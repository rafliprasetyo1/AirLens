# Proyek Wokwi: latihan AirLens Beta tanpa alat

Simulasi ESP32 DevKit + empat sensor gas (diberi nama MQ-2, MQ-3, MQ-7, MQ-135) di GPIO34/35/32/33, masing-masing lewat
pembagi 10 kΩ / 20 kΩ seperti alat asli. Sketch-nya (`beta/sketch.ino`) identik dengan firmware Beta
(`firmware/beta/beta.ino`): baca empat ADC tiap 2 detik, cetak JSON di Serial, dan kirim ke AirLens lewat HTTPS
(alamat ngrok) bila WiFi dan URL sudah diatur.

## Cara membuka (tanpa instalasi)

1. Buka https://wokwi.com, pilih **New Project → ESP32**.
2. Tab `diagram.json`: ganti isinya dengan `wokwi/beta/diagram.json`.
3. Tab `sketch.ino`: ganti isinya dengan `wokwi/beta/sketch.ino`.
4. Tambah berkas baru (tombol ▾ di samping tab → **New file**) bernama `airlens_roots.h`, isi dengan
   `wokwi/beta/airlens_roots.h` (sertifikat akar Let's Encrypt untuk domain ngrok).
5. Klik **Run** (▶).

## Yang terlihat

- Serial Monitor mencetak `{"event":"boot",...}`, lalu satu baris JSON tiap 2 detik, misalnya
  `{"node_id":"lite-01","uptime_s":12,"mq2_mv":...,"mq3_mv":...,"mq7_mv":...,"mq135_mv":...}`.
- Klik salah satu sensor gas lalu geser nilai **ppm**: tegangannya naik dan angka mV di Serial ikut berubah.

## Mengirim ke AirLens (ngrok)

Pastikan AirLens menyala dengan alamat ngrok (`make expo-setup` atau `make expo-public`). Ketik satu baris ini di
kotak input Serial Monitor (ganti `<NGROK_DOMAIN>` dan `<SENSOR_TOKEN>` dengan nilai dari `.env`; token cukup
diketik di sini, jangan disimpan di proyek Wokwi):

```
SET {"ssid":"Wokwi-GUEST","pass":"","url":"https://<NGROK_DOMAIN>/api/sensor/readings","token":"<SENSOR_TOKEN>","node":"wokwi-01"}
```

Serial Monitor menjawab `{"event":"saved",...}`, lalu `{"event":"wifi","status":"connected",...}`. Setelah itu buka
`https://<NGROK_DOMAIN>/beta.html`: node `wokwi-01` muncul. Server menunggu 3 menit pemanasan dan 24 bacaan untuk
baseline udara bersih (biarkan ppm rendah), lalu model dan SHAP mulai bekerja. Naikkan ppm MQ-2 dan MQ-135 untuk
melihat kelas dan waterfall SHAP berubah.

`GET` menampilkan pengaturan tersimpan (kata sandi dan token tidak pernah dicetak). `CLEAR` menghapus semuanya.

## Keterbatasan simulator

- Komponen gas Wokwi adalah model sederhana: satu angka ppm → satu tegangan. Ia tidak meniru kepekaan silang antar
  gas, pemanasan, atau drift MQ sungguhan. Pola yang dikenali model (asap vs alkohol) hanya muncul bila keempat
  slider digeser sesuai pola gas; hasilnya **bukan** bukti akurasi.
- Bacaan Wokwi tidak memakai label "Simulated" (sketch sama dengan alat asli). Pakai nama node yang jelas, misalnya
  `wokwi-01`, agar tidak tertukar dengan alat di booth.
- Wokwi-GUEST butuh internet; HTTPS ke ngrok berjalan lewat gateway Wokwi dan bisa lebih lambat daripada alat asli.
- Kecepatan simulasi bisa di bawah waktu nyata pada komputer lambat, sehingga jarak antar bacaan bisa lebih dari
  2 detik.
