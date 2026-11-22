# Perintah AirLens yang sering dipakai

Semua perintah dijalankan di terminal WSL (Ubuntu), dari folder proyek:

```bash
cd ~/AirLens
export PATH="$HOME/.local/bin:$PATH"   # sekali per terminal: agar ngrok ditemukan
```

Urutan lengkap per kesempatan: sesi lab di [AirLens_perintah_lab.txt](../AirLens_perintah_lab.txt), hari pameran di
[EXPO_HARI_H.txt](EXPO_HARI_H.txt). Penjelasan pameran dan ngrok di [EXPO.md](EXPO.md).

## Cek kesiapan

| Perintah | Fungsi |
|---|---|
| `make doctor` | Cek semuanya: `.env`, ngrok, Kaggle, data darurat, layanan, model aktif, keamanan endpoint. Tiap masalah disertai perintah perbaikannya. Ulangi sampai `HASIL: siap` |
| `make ps` | Layanan mana yang jalan dan sehat |
| `make logs` | Log semua layanan (Ctrl+C untuk keluar) |

## Menyalakan dan mematikan

| Perintah | Fungsi |
|---|---|
| `make expo-setup` | Satu perintah untuk pameran: doctor, mode expo (token wajib), ambil model final dari Kaggle, nyalakan layanan, ngrok, QR (`docs/assets/qr_expo.png`). Aman diulang |
| `make expo-setup PROFILE=lab` | Sama, di komputer lab |
| `make up` | Nyalakan layanan saja (website, API, database, MLflow, penjadwal) |
| `make down` | Matikan semua layanan |
| `docker compose -f compose.yaml up -d --build web` | Bangun ulang website setelah file di `web/` diubah |

## Akses dari HP (ngrok)

| Perintah | Fungsi |
|---|---|
| `make expo-public` | Nyalakan ngrok. Alamat publik dicetak dan disimpan ke `.env` (`NGROK_DOMAIN`) |
| `make expo-public-stop` | Matikan ngrok (layanan Docker tetap jalan) |
| `grep ^NGROK_DOMAIN= .env` | Lihat alamat ngrok sesi ini |

Alamat ngrok gratis **berganti setiap ngrok dinyalakan ulang**. Setelah itu: perbarui URL di ESP32 (flash.html, Set WiFi)
dan tampilkan QR baru. Pertama kali dibuka, ngrok gratis menampilkan halaman peringatan; tekan *Visit Site*.

## Gladi tanpa alat (Wokwi)

| Perintah | Fungsi |
|---|---|
| `make gladi` | Buka jalur HTTP sementara untuk ESP32 simulasi di Wokwi, cetak perintah `SET` siap tempel |
| `make gladi-stop` | Tutup jalur, hapus data node `wokwi-*`, ganti token, nyalakan ulang API. **Wajib setelah gladi** |
| `make gladi-stop KEEP_TOKENS=1` | Sama, tetapi token tidak diganti (bila ESP32 asli sudah menyimpan token yang sama) |

Langkah di Wokwi dan kombinasi uji: [wokwi/README.md](../wokwi/README.md).

## Token dan rahasia

| Perintah | Fungsi |
|---|---|
| `make tokens` | Isi `SENSOR_TOKEN` dan `NODE_TOKEN` acak di `.env` bila masih kosong |
| `make tokens ROTATE=1` | Ganti kedua token; lalu `docker compose -f compose.yaml up -d api` dan simpan token baru ke ESP32 |
| `grep ^SENSOR_TOKEN= .env` | Lihat token untuk diisi di flash.html atau perintah `SET` (jangan ditempel di chat atau repo) |
| `make vapid-keys` | Buat kunci Web Push sekali (notifikasi HP). Salin ke `.env` komputer lab agar langganan notifikasi tetap berlaku |

## Model (pelatihan hanya di Kaggle, tidak di laptop)

| Perintah | Fungsi |
|---|---|
| `make kaggle-push` | Kirim kode dan jalankan pelatihan di Kaggle (GPU) |
| `make kaggle-status` | Status pelatihan |
| `make kaggle-pull` | Ambil arsip hasil ke `results/` |
| `make import-results ARCHIVE=results/<arsip>.tar.gz` | Daftarkan hasil sebagai challenger untuk diperiksa |
| `make import-results ARCHIVE=... ALIAS=production CONFIRM=1` | Jadikan production setelah metrik disetujui |
| `make models-publish MODELS_APPROVED=1` | Terbitkan model production ke dataset Kaggle privat `airlens-models` |
| `make models-pull` | Ambil model final (di komputer lain atau komputer lab). `VERSION=n` untuk versi tertentu |
| `make rollback` / `make rollback-beta` | Kembalikan model foto / model gas ke versi sebelumnya |

## Alat Beta (ESP32 + empat MQ)

| Perintah / alamat | Fungsi |
|---|---|
| `http://localhost:8080/tools/flash.html` | Flash firmware dan simpan WiFi, URL ngrok, token, interval ke ESP32 (Chrome/Edge, kabel USB data). Hanya dari komputer ini |
| `http://localhost:8080/tools/recorder.html` | Rekam data kalibrasi berlabel ke CSV |
| `make import-beta-recordings CSV=<berkas.csv>` | Evaluasi model gas dengan rekaman alat sendiri (di laptop) |
| `make beta-recordings-push CSV=<berkas.csv>` lalu `make kaggle-push` | Latih ulang model gas di Kaggle dengan rekaman alat |
| `make firmware-beta` | Kompilasi ulang firmware (`beta.bin`) setelah `firmware/beta/beta.ino` diubah; sketch Wokwi ikut disamakan |
| `make data-beta` | Unduh data MultimodalGasData (±330 KB, tanpa pelatihan); dibutuhkan simulator darurat |
| `python3 scripts/sensor_sim.py --replay dataset` | Simulator sensor berlabel "Simulated" bila internet putus atau sensor rusak (Ctrl+C berhenti) |

## Casing cetak 3D

| File | Keterangan |
|---|---|
| `hardware/enclosure-beta/stl/airlens_beta_base.stl` | Nampan; lantai di bed, tanpa support |
| `hardware/enclosure-beta/stl/airlens_beta_lid.stl` | Tutup; **dibalik** (permukaan atas di bed), tanpa support |

Pengaturan cetak, perlengkapan, dan cara membuat ulang: [hardware/enclosure-beta/README.md](../hardware/enclosure-beta/README.md#file-untuk-cetak-3d).
Ukur modul MQ dan breadboard asli dulu sebelum mencetak.

## Pengujian

| Perintah | Fungsi |
|---|---|
| `make test` | Tes unit (±25 menit) |
| `make ui-test` | Uji tampilan di Chrome headless; tangkapan layar dan laporan di `results/ui/` |

## Git (pemilik yang push)

| Perintah | Fungsi |
|---|---|
| `git status` | File yang berubah |
| `git log --oneline -5` | Commit terakhir |
| `git push` | Kirim commit ke GitHub |
| `git clone https://github.com/rafliprasetyo1/AirLens.git` | Ambil proyek pertama kali di komputer baru (dari folder `~`) |
| `git pull` | Ambil kode terbaru (komputer lab) |
| `git fetch origin && git reset --hard origin/main` | Samakan clone lama dengan GitHub bila `git pull` gagal (riwayat sempat ditulis ulang). `.env`, `results/`, `data/` tidak tersentuh |

## Darurat saat pameran

| Masalah | Perintah |
|---|---|
| Internet putus | Layar booth tetap `http://localhost:8080`; `python3 scripts/sensor_sim.py --replay dataset` |
| ngrok putus / alamat berubah | `make expo-public`, lalu perbarui URL ESP32 (flash.html) dan QR |
| Layanan mati / halaman error | `make expo-setup PROFILE=lab`; lihat `make logs` |
| Model hilang atau salah | `make models-pull` |
| Kuota ngrok habis | Pengunjung melihat layar booth (localhost) |

## Selesai di komputer lab (bila dipakai orang lain)

```bash
make expo-public-stop
docker compose -f compose.yaml down
rm -f .env ~/.config/ngrok/ngrok.yml
```
