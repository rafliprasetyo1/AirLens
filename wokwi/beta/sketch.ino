// AirLens Beta: ESP32 DevKit + 4 sensor gas MQ (MQ-2, MQ-3, MQ-7, MQ-135).
//
// Setiap 2 detik: baca tegangan keempat pin ADC (rata-rata 16 sampel, analogReadMilliVolts), cetak satu baris JSON
// di Serial (dibaca tools/recorder.html), dan bila WiFi + URL tersimpan, kirim JSON yang sama ke AirLens lewat HTTPS:
//   POST https://<NGROK_DOMAIN>/api/sensor/readings
//   {"node_id":"lite-01","uptime_s":125,"mq2_mv":812,"mq3_mv":640,"mq7_mv":905,"mq135_mv":701}
// Server yang menghitung Rs, baseline udara bersih, model AI, dan SHAP. Alat ini hanya mengukur dan mengirim.
//
// WiFi, kata sandi, URL server, token, dan nama node TIDAK ditulis di kode. Semuanya dikirim lewat Serial dari
// halaman tools/flash.html, lalu disimpan di NVS (Preferences). Perintah Serial (satu baris, 115200 baud):
//   SET {"ssid":"...","pass":"...","url":"https://.../api/sensor/readings","token":"...","node":"lite-01","interval":"2"}
//   GET      -> pengaturan tersimpan (kata sandi dan token tidak pernah dicetak, hanya "ada/tidak")
//   CLEAR    -> hapus semua pengaturan
//   REBOOT
//
// HTTPS: sertifikat server diverifikasi terhadap akar Let's Encrypt (ISRG Root X1, X2, YE) di airlens_roots.h, yang
// dipakai domain ngrok. Tidak memakai setInsecure(). Jam disinkronkan lewat NTP sebelum koneksi pertama.
// Pin: hanya ADC1 (GPIO32-39), karena ADC2 tidak bisa dibaca saat WiFi menyala. Setiap AO MQ lewat pembagi
// 10 kΩ / 20 kΩ, sehingga 5 V menjadi ±3,3 V di pin.

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <time.h>
#include "airlens_roots.h"

#define FW_VERSION "beta-4mq-1.1.2"

const int PIN_MQ2 = 34, PIN_MQ3 = 35, PIN_MQ7 = 32, PIN_MQ135 = 33;
unsigned long periodMs = 2000;              // jarak bacaan; bawaan 2 s, diatur lewat SET {"interval":"10"}
const int SAMPLES = 16;                     // rata-rata untuk meredam derau ADC

Preferences prefs;
String ssid, pass, url, token, nodeId;
unsigned long lastRead = 0, lastWifiTry = 0;
bool timeSynced = false;
bool sntpStarted = false;                         // configTime sekali per sambungan WiFi
bool postOkShown = false;                         // cetak satu kali "post 200" per sambungan (tanda berhasil)
unsigned long lastTimeMsg = 0;
String line;                                // baris perintah Serial yang sedang diketik

void loadSettings() {
  prefs.begin("airlens", true);
  ssid = prefs.getString("ssid", "");
  pass = prefs.getString("pass", "");
  url = prefs.getString("url", "");
  token = prefs.getString("token", "");
  nodeId = prefs.getString("node", "lite-01");
  periodMs = (unsigned long)constrain(prefs.getString("interval", "2").toInt(), 2L, 60L) * 1000UL;
  prefs.end();
}

// Ambil nilai string dari JSON datar sederhana {"k":"v",...}. Cukup untuk perintah SET dari halaman alat.
String jsonValue(const String& json, const char* key) {
  String pat = String("\"") + key + "\"";
  int k = json.indexOf(pat);
  if (k < 0) return String();
  int colon = json.indexOf(':', k + pat.length());
  int q1 = json.indexOf('"', colon + 1);
  if (colon < 0 || q1 < 0) return String();
  String out;
  for (int i = q1 + 1; i < (int)json.length(); i++) {
    char c = json[i];
    if (c == '\\' && i + 1 < (int)json.length()) { out += json[++i]; continue; }
    if (c == '"') return out;
    out += c;
  }
  return String();
}

bool hasKey(const String& json, const char* key) { return json.indexOf(String("\"") + key + "\"") >= 0; }

void printSettings() {
  Serial.printf("{\"event\":\"settings\",\"fw\":\"%s\",\"node\":\"%s\",\"ssid\":\"%s\",\"url\":\"%s\","
                "\"interval_s\":%lu,\"has_pass\":%s,\"has_token\":%s}\n", FW_VERSION, nodeId.c_str(), ssid.c_str(),
                url.c_str(), periodMs / 1000, pass.length() ? "true" : "false", token.length() ? "true" : "false");
}

void handleCommand(String cmd) {
  cmd.trim();
  if (cmd.startsWith("SET ")) {
    String json = cmd.substring(4);
    prefs.begin("airlens", false);
    String saved;
    const char* keys[] = {"ssid", "pass", "url", "token", "node", "interval"};
    for (const char* k : keys) {
      if (hasKey(json, k)) {
        prefs.putString(k, jsonValue(json, k));
        saved += String(saved.length() ? "," : "") + "\"" + k + "\"";
      }
    }
    prefs.end();
    loadSettings();
    WiFi.disconnect();
    lastWifiTry = 0;
    timeSynced = false;
    sntpStarted = false;
    Serial.printf("{\"event\":\"saved\",\"keys\":[%s]}\n", saved.c_str());
    printSettings();
  } else if (cmd == "GET") {
    printSettings();
  } else if (cmd == "CLEAR") {
    prefs.begin("airlens", false);
    prefs.clear();
    prefs.end();
    loadSettings();
    WiFi.disconnect();
    Serial.println("{\"event\":\"cleared\"}");
  } else if (cmd == "REBOOT") {
    Serial.println("{\"event\":\"reboot\"}");
    delay(100);
    ESP.restart();
  } else if (cmd.length()) {
    Serial.println("{\"event\":\"error\",\"detail\":\"perintah tidak dikenal (SET/GET/CLEAR/REBOOT)\"}");
  }
}

void readSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (line.length()) handleCommand(line);
      line = "";
    } else if (line.length() < 600) {
      line += c;
    }
  }
}

void ensureWifi() {
  if (!ssid.length() || WiFi.status() == WL_CONNECTED) return;
  if (lastWifiTry && millis() - lastWifiTry < 15000) return;   // coba lagi tiap 15 detik, tanpa memblokir
  lastWifiTry = millis();
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid.c_str(), pass.c_str());
  Serial.printf("{\"event\":\"wifi\",\"status\":\"connecting\",\"ssid\":\"%s\"}\n", ssid.c_str());
}

// Jam dari internet (NTP) dibutuhkan untuk memeriksa sertifikat HTTPS. configTime() hanya dipanggil SEKALI per sambungan
// WiFi: memanggilnya ulang memulai sinkronisasi dari nol, sehingga di jaringan lambat (Wokwi, WiFi lab) jam tidak pernah
// siap dan tidak ada data terkirim (bug v1.1.0). Pemeriksaan jam tidak memblokir pembacaan sensor.
void syncTime() {
  if (WiFi.status() != WL_CONNECTED) { sntpStarted = false; postOkShown = false; return; }
  if (!sntpStarted) {
    sntpStarted = true;
    configTime(0, 0, "pool.ntp.org", "time.google.com");
    Serial.printf("{\"event\":\"wifi\",\"status\":\"connected\",\"ip\":\"%s\",\"time\":\"%s\"}\n",
                  WiFi.localIP().toString().c_str(), timeSynced ? "ok" : "syncing");
    lastTimeMsg = millis();
  }
  if (timeSynced) return;
  struct tm t;
  if (getLocalTime(&t, 0)) {
    timeSynced = true;
    Serial.println("{\"event\":\"time\",\"status\":\"ok\"}");
  } else if (millis() - lastTimeMsg >= 10000) {
    lastTimeMsg = millis();
    Serial.println("{\"event\":\"time\",\"status\":\"waiting\"}");   // jaringan mungkin memblokir NTP (UDP 123)
  }
}

int readMv(int pin) {
  long sum = 0;
  for (int i = 0; i < SAMPLES; i++) sum += analogReadMilliVolts(pin);
  return (int)(sum / SAMPLES);
}

// Klien dibuat sekali dan koneksi dipakai ulang (keep-alive): handshake TLS ±1 s tidak diulang tiap 2 detik.
WiFiClientSecure secure;
WiFiClient plain;
HTTPClient http;

void post(const String& body) {
  if (!url.length() || WiFi.status() != WL_CONNECTED) return;
  bool https = url.startsWith("https://");
  if (https) {
    if (!timeSynced) return;                       // validasi sertifikat butuh jam yang benar
    if (!http.begin(secure, url)) return;
  } else {
    if (!http.begin(plain, url)) return;           // http:// hanya untuk uji lokal (localhost/LAN), bukan pameran
  }
  http.setReuse(true);
  http.setTimeout(8000);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("ngrok-skip-browser-warning", "1");
  if (token.length()) http.addHeader("X-Node-Token", token);
  int code = http.POST(body);
  if (code < 0 && https) {                         // gagal sebelum ada balasan HTTP: tampilkan galat TLS/koneksi aslinya
    char err[96] = "";
    secure.lastError(err, sizeof(err));
    for (char* c = err; *c; c++) if (*c == '"' || *c == '\\') *c = '\'';
    Serial.printf("{\"event\":\"post\",\"code\":%d,\"detail\":\"%s\",\"tls\":\"%s\"}\n", code,
                  HTTPClient::errorToString(code).c_str(), err);
    postOkShown = false;
  } else if (code != 200) { Serial.printf("{\"event\":\"post\",\"code\":%d}\n", code); postOkShown = false; }
  else if (!postOkShown) { postOkShown = true; Serial.println("{\"event\":\"post\",\"code\":200}"); }
  http.end();
}

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);                  // rentang pin ±0-3,1 V
  secure.setCACert(AIRLENS_ROOT_CAS);              // akar Let's Encrypt untuk domain ngrok (bukan setInsecure)
  loadSettings();
  Serial.printf("{\"event\":\"boot\",\"fw\":\"%s\"}\n", FW_VERSION);
  printSettings();
}

void loop() {
  readSerial();
  ensureWifi();
  syncTime();
  if (millis() - lastRead >= periodMs) {
    lastRead = millis();
    char body[200];
    snprintf(body, sizeof(body),
             "{\"node_id\":\"%s\",\"uptime_s\":%lu,\"mq2_mv\":%d,\"mq3_mv\":%d,\"mq7_mv\":%d,\"mq135_mv\":%d}",
             nodeId.c_str(), millis() / 1000, readMv(PIN_MQ2), readMv(PIN_MQ3), readMv(PIN_MQ7), readMv(PIN_MQ135));
    Serial.println(body);
    post(String(body));
  }
}
