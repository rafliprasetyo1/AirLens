# Proyek Wokwi: latihan AirLens Beta tanpa alat

Simulasi ESP32 DevKit + empat sensor gas (diberi nama MQ-2, MQ-3, MQ-7, MQ-135) di GPIO34/35/32/33. Sketch-nya
(`beta/sketch.ino`) identik dengan firmware Beta (`firmware/beta/beta.ino`): baca empat ADC tiap 2 detik, cetak JSON di
Serial, dan kirim ke AirLens bila WiFi dan URL sudah diatur.

**Beda dengan alat asli:** di Wokwi, AOUT tiap sensor tersambung **langsung** ke GPIO, tanpa pembagi 10 kΩ / 20 kΩ.
Wokwi tidak menyimulasikan resistor bersama komponen analog ("You won't be able to use resistors together with analog
components", docs.wokwi.com/parts/wokwi-resistor): dengan pembagi, pin membaca angka tetap berapa pun ppm-nya. Alat asli
**wajib** memakai pembagi (5 V dari sensor menjadi ±3,3 V di pin ESP32); ikuti panduan perakitan, bukan gambar ini.
Kabel sinyal berwarna sama dengan model 3D dan grafik halaman Beta (MQ-2 biru, MQ-3 kuning, MQ-7 ungu, MQ-135 hijau).

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

## Kombinasi uji (setelah status Normal di halaman Beta)

Model membaca rasio terhadap udara bersih, jadi patokannya angka mV di Serial, bukan ppm. Naikkan ppm sensor yang
disebut sampai `mqX_mv`-nya minimal **2× nilai awal** (nilai saat semua 400 ppm); sensor lain biarkan.
Dihitung dengan model `airlens-beta-gas/6`:

| Uji | Sensor dinaikkan | Hasil | Halaman Beta |
|---|---|---|---|
| Udara bersih | tidak ada | clean air 97 % | Normal |
| Asap | MQ-3 + MQ-135 | smoke 100 % | Alert + notifikasi |
| Asap (sederhana) | MQ-135 | smoke 90 % | Alert + notifikasi |
| Asap + alkohol | MQ-2 + MQ-3 + MQ-7 | smoke + alcohol 99 % | Alert + notifikasi |
| Alkohol | MQ-2 + MQ-7 | alcohol 93 % | Ditampilkan, tanpa peringatan |

MQ-2 saja dinilai clean air (68 %): model belajar dari sensor tim lain; dilatih ulang dengan rekaman alat sendiri.
Wokwi bukan sensor fisik, jadi ini uji alur, bukan uji akurasi.

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
