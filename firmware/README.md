# Firmware AirLens Beta

| Sketch | Papan | Fungsi |
|---|---|---|
| `beta/beta.ino` | ESP32 DevKit (ESP32-WROOM-32) | 4 sensor gas MQ-2/MQ-3/MQ-7/MQ-135 di GPIO34/35/32/33, kirim mV tiap 2 s (bisa diatur 2–60 s) |

Firmware mengirim lewat **HTTPS ke alamat ngrok** (`https://<NGROK_DOMAIN>/api/...`), alamat sesi ngrok (akun free: berganti tiap sesi, diperbarui lewat
Set WiFi tanpa flash ulang). Sertifikat server diverifikasi terhadap akar Let's Encrypt yang dipakai
domain ngrok (ISRG Root X1, X2, YE di `certs/`, diubah menjadi `airlens_roots.h` oleh skrip build). `setInsecure()`
tidak dipakai. WiFi, kata sandi, URL, token (`SENSOR_TOKEN`), dan nama node tidak ada di kode; semuanya dikirim
lewat Serial dari `http://localhost:8080/tools/flash.html` dan disimpan di NVS.

## Cara pakai (tanpa memasang apa pun)

1. `make expo-setup` atau `docker compose up -d web`, lalu buka `http://localhost:8080/tools/flash.html` di Chrome.
2. Hubungkan ESP32 lewat USB, klik **Connect**, pilih firmware, **Flash**.
3. Isi formulir **Set WiFi** (SSID, kata sandi, URL server, token) lalu **Save to device**.

Berkas `.bin` siap flash (bootloader + partisi + aplikasi, offset 0x0) ada di `web/static/tools/firmware/` beserta
`manifest.json` (versi, ukuran, sha256).

## Kompilasi ulang (hanya di laptop pengembang)

Toolchain dipasang sekali di folder pengguna, tanpa sudo (±1,5 GB, termasuk toolchain semua varian ESP32):

```bash
mkdir -p ~/.local/bin
curl -sSL https://downloads.arduino.cc/arduino-cli/arduino-cli_1.3.1_Linux_64bit.tar.gz | tar -xz -C ~/.local/bin arduino-cli
arduino-cli config init
arduino-cli config set board_manager.additional_urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli config set network.connection_timeout 1800s
arduino-cli core update-index
arduino-cli core install esp32:esp32@3.3.13
make firmware-beta
```

Lewat Arduino IDE juga bisa: buka `beta/beta.ino`, pilih papan "ESP32 Dev Module",
lalu Upload. Header `airlens_roots.h` sudah ada di folder sketch.

## Sertifikat

Domain dev ngrok (`*.ngrok-free.app`, `*.ngrok-free.dev`) memakai rantai Let's Encrypt YE2 → Root YE (cross-sign
ISRG Root X2 → X1), diperiksa 2026-11-21. Firmware membawa ketiga akar sehingga tetap valid ketika Let's Encrypt
berhenti mengirim cross-sign. Masa berlaku: X1 sampai 2035, X2 sampai 2040, YE sampai 2045. Bila suatu saat ngrok
berganti CA, perbarui `certs/`, jalankan `make firmware-beta`, lalu flash ulang.
