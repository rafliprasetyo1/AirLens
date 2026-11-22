// Flash firmware Beta dari browser (Web Serial + esptool-js 0.7.0 lokal) lalu kirim pengaturan WiFi lewat Serial.
// Kata sandi dan token hanya lewat USB ke perangkat: tidak disimpan di browser, tidak dikirim ke server AirLens.
import { ESPLoader, Transport } from "/vendor/esptool-js-0.7.0/bundle.js";

const $ = (id) => document.getElementById(id);
const el = {
  noSerial: $("no-serial"), list: $("fw-list"), connect: $("connect"), flash: $("flash"), disconnect: $("disconnect"),
  status: $("flash-status"), progress: $("progress"), form: $("wifi-form"), save: $("save"), read: $("read"),
  wifiStatus: $("wifi-status"), log: $("log"), url: $("url"), pass: $("pass"), token: $("token"), node: $("node"),
  ssid: $("ssid"), interval: $("interval"), intervalField: $("interval-field"), urlHint: $("url-hint"),
};
const PATHS = { beta: "/api/sensor/readings" };
let manifest = null, port = null, monitor = null;

function say(node, text, kind = "") { node.textContent = text; node.dataset.kind = kind; }
function log(text) {
  el.log.textContent += text.endsWith("\n") ? text : `${text}\n`;
  if (el.log.textContent.length > 20000) el.log.textContent = el.log.textContent.slice(-15000);
  el.log.scrollTop = el.log.scrollHeight;
}
const chosen = () => (document.querySelector('input[name="fw"]:checked') || {}).value || "beta";

function defaultUrl() {
  // Lewat ngrok (https) alamat halaman ini = alamat yang dipakai alat. Lewat localhost, operator mengisi alamat ngrok.
  const path = PATHS[chosen()];
  if (location.protocol === "https:") return `${location.origin}${path}`;
  return "";
}
function onFirmwareChange() {
  if (!el.node.dataset.touched) el.node.value = "lite-01";
  if (!el.interval.dataset.touched) el.interval.value = 2;
  if (!el.url.dataset.touched) el.url.value = defaultUrl();
  el.urlHint.textContent = `The ngrok address of this session, for example https://name.ngrok-free.app${PATHS[chosen()]}`;
}
el.node.addEventListener("input", () => { el.node.dataset.touched = "1"; });
el.url.addEventListener("input", () => { el.url.dataset.touched = "1"; });
el.interval.addEventListener("input", () => { el.interval.dataset.touched = "1"; });

async function loadManifest() {
  try {
    const r = await fetch("/tools/firmware/manifest.json", { cache: "no-store" });
    if (!r.ok) throw new Error(String(r.status));
    manifest = await r.json();
  } catch {
    el.list.replaceChildren(Object.assign(document.createElement("li"), {
      textContent: "Firmware files are missing. On the developer laptop run: make firmware-beta" }));
    return;
  }
  el.list.replaceChildren(...Object.entries(manifest.files).map(([key, f], i) => {
    const li = document.createElement("li");
    const label = document.createElement("label");
    const input = Object.assign(document.createElement("input"), { type: "radio", name: "fw", value: key, checked: i === 0 });
    input.addEventListener("change", onFirmwareChange);
    const text = document.createElement("span");
    text.textContent = "AirLens Beta: 4 MQ gas sensors";
    const small = document.createElement("small");
    small.textContent = `${f.board} · ${f.version} · ${(f.bytes / 1024).toFixed(0)} KB · sha256 ${f.sha256.slice(0, 12)}…`;
    text.append(small);
    label.append(input, text);
    li.append(label);
    return li;
  }));
  onFirmwareChange();
}

// ------------------------------------------------------------------ monitor serial (baris JSON dari firmware)
async function openMonitor() {
  if (!port || monitor) return;
  await port.open({ baudRate: 115200 });
  const decoder = new TextDecoderStream();
  const closed = port.readable.pipeTo(decoder.writable).catch(() => {});
  const reader = decoder.readable.getReader();
  const encoder = new TextEncoderStream();
  const writerClosed = encoder.readable.pipeTo(port.writable).catch(() => {});
  monitor = { reader, writer: encoder.writable.getWriter(), closed, writerClosed };
  el.save.disabled = el.read.disabled = false;
  (async () => {
    let buf = "";
    try {
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += value;
        let i;
        while ((i = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, i).trim();
          buf = buf.slice(i + 1);
          if (line) onLine(line);
        }
      }
    } catch { /* port ditutup */ }
  })();
}

async function closeMonitor() {
  if (!monitor) return;
  const m = monitor;
  monitor = null;
  el.save.disabled = el.read.disabled = true;
  try { await m.reader.cancel(); } catch { /* sudah tertutup */ }
  await m.closed;
  try { await m.writer.close(); } catch { /* sudah tertutup */ }
  await m.writerClosed;
  try { await port.close(); } catch { /* sudah tertutup */ }
}

function onLine(line) {
  log(line);
  let msg;
  try { msg = JSON.parse(line); } catch { return; }
  if (msg.event === "settings") {
    say(el.wifiStatus, `Device ${msg.fw}: node ${msg.node}, WiFi "${msg.ssid || "-"}", URL ${msg.url || "-"}, `
      + `password ${msg.has_pass ? "saved" : "not set"}, token ${msg.has_token ? "saved" : "not set"}.`, "ok");
  } else if (msg.event === "wifi" && msg.status === "connected") {
    say(el.wifiStatus, msg.time === "syncing" ? `Connected to WiFi (IP ${msg.ip}). Getting the time from the internet before sending…`
      : `Connected to WiFi (IP ${msg.ip}). Readings are being sent.`, "ok");
  } else if (msg.event === "time") {
    if (msg.status === "ok") say(el.wifiStatus, "Clock synced. Readings are being sent.", "ok");
    else say(el.wifiStatus, "Still waiting for the internet time (NTP). The network may block NTP (UDP port 123).", "error");
  } else if (msg.event === "post" || msg.event === "frame") {
    if (msg.code === 200) say(el.wifiStatus, "Readings reach AirLens (HTTP 200).", "ok");
    else if (msg.code === 401) say(el.wifiStatus, "The server rejected the token (401). Check SENSOR_TOKEN.", "error");
    else if (msg.code < 0) say(el.wifiStatus, `Could not reach the server (code ${msg.code}). Check the URL and internet.`, "error");
  }
}

async function send(text) {
  if (!monitor) return;
  await monitor.writer.write(`${text}\n`);
}

// ------------------------------------------------------------------ tombol
el.connect.addEventListener("click", async () => {
  try {
    port = await navigator.serial.requestPort();
  } catch {
    say(el.status, "No device selected.", "error");
    return;
  }
  el.flash.disabled = !manifest;
  el.disconnect.disabled = false;
  el.connect.disabled = true;
  say(el.status, "Device connected. You can flash it, or save settings if the firmware is already installed.", "ok");
  try { await openMonitor(); } catch (e) { log(`monitor: ${e.message}`); }
});

el.disconnect.addEventListener("click", async () => {
  await closeMonitor();
  port = null;
  el.flash.disabled = el.disconnect.disabled = true;
  el.connect.disabled = false;
  say(el.status, "Device disconnected.");
});

async function sha256(bytes) {
  const h = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(h), (b) => b.toString(16).padStart(2, "0")).join("");
}

el.flash.addEventListener("click", async () => {
  const f = manifest.files[chosen()];
  el.flash.disabled = el.disconnect.disabled = true;
  el.progress.hidden = false;
  el.progress.value = 0;
  try {
    say(el.status, "Downloading firmware…");
    const data = new Uint8Array(await (await fetch(`/tools/firmware/${f.file}`, { cache: "no-store" })).arrayBuffer());
    if ((await sha256(data)) !== f.sha256) throw new Error("firmware file is damaged (sha256 mismatch); reload the page");
    await closeMonitor();
    const terminal = { clean() {}, writeLine: (t) => log(t), write: (t) => log(t) };
    const transport = new Transport(port, false);
    const loader = new ESPLoader({ transport, baudrate: 460800, romBaudrate: 115200, terminal });
    say(el.status, "Connecting to the chip (hold BOOT if it does not respond)…");
    const chip = await loader.main();
    say(el.status, `Flashing ${chip}…`);
    await loader.writeFlash({
      fileArray: [{ data, address: 0 }], flashMode: "keep", flashFreq: "keep", flashSize: "keep",
      eraseAll: false, compress: true,
      reportProgress: (_i, written, total) => { el.progress.value = Math.round((written / total) * 100); },
    });
    await loader.after("hard_reset");
    await transport.disconnect();
    say(el.status, `Done: ${f.version} installed. The device restarts; now save the WiFi settings below.`, "ok");
    await openMonitor();
  } catch (e) {
    say(el.status, `Flashing failed: ${e.message || e}`, "error");
    log(String(e && e.stack || e));
  } finally {
    el.flash.disabled = el.disconnect.disabled = false;
  }
});

el.form.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  if (!el.form.reportValidity()) return;
  const settings = { ssid: el.ssid.value, pass: el.pass.value, url: el.url.value.trim(), node: el.node.value.trim() };
  if (el.token.value) settings.token = el.token.value;
  settings.interval = String(el.interval.value || 2);
  if (!/^https?:\/\//.test(settings.url)) { say(el.wifiStatus, "The server URL must start with https://", "error"); return; }
  if (settings.url.startsWith("http://") && !/^http:\/\/(localhost|127\.)/.test(settings.url)) {
    say(el.wifiStatus, "Use the https:// ngrok address; plain http is only for local tests.", "error");
    return;
  }
  await send(`SET ${JSON.stringify(settings)}`);
  // Rahasia tidak dibiarkan tertinggal di formulir.
  el.pass.value = "";
  el.token.value = "";
  say(el.wifiStatus, "Settings sent. Waiting for the device to confirm…");
});

el.read.addEventListener("click", () => send("GET"));

if (!("serial" in navigator)) {
  el.noSerial.hidden = false;
  el.connect.disabled = true;
  say(el.status, "Connect a device: not available in this browser.", "error");
}
loadManifest();
