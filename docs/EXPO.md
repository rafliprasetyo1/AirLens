# AirLens di pameran (komputer lab, ngrok penuh)

Pada hari pameran **komputer lab** yang menjalankan AirLens. Semua akses dari luar komputer itu (HP pengunjung, ESP32
Beta) lewat **ngrok** (HTTPS publik). Tidak ada IP lokal/LAN. Layar booth membuka `http://localhost:8080`
di komputer lab sendiri. Daftar perintah hari H: [EXPO_HARI_H.txt](EXPO_HARI_H.txt).

## 1. Sebelum hari pameran (di laptop)

1. Model final dilatih di Kaggle (`make kaggle-push`, `make kaggle-pull`), diperiksa, lalu diterbitkan:
   `make models-publish MODELS_APPROVED=1` (dataset Kaggle privat `airlens-models`).
2. Kode di-push ke GitHub (oleh pemilik), supaya komputer lab tinggal `git pull`.
3. Siapkan isi `.env` untuk lab (dibawa sendiri, tidak lewat repo): POSTGRES_PASSWORD, IQAIR_API_KEY, KAGGLE_USERNAME,
   KAGGLE_KEY, VAPID_* (salin dari laptop agar subscription notifikasi tetap berlaku), SENSOR_TOKEN, NODE_TOKEN.
   Token sensor harus SAMA dengan yang disimpan di ESP32.

## 2. Satu perintah: `make expo-setup`

`doctor` → `models-pull` (model final dari Kaggle) → layanan pameran (db, mlflow, api, web) dalam **mode expo** →
ngrok → QR. Keluaran: alamat publik, URL sensor untuk ESP32, alamat halaman alat, dan QR di terminal +
`docs/assets/qr_expo.png`. Aman diulang (layanan mati, ngrok putus, komputer restart).

## 3. ngrok (akun free)

- Alamat ngrok free **berganti tiap sesi**. `make expo-public` (dipanggil `expo-setup`) menjalankan ngrok di latar,
  membaca alamat sesi dari API lokal ngrok, lalu **menyimpan/menimpa** `NGROK_DOMAIN` di `.env`.
- Bila ngrok di-restart: jalankan ulang `make expo-public` (atau `make expo-setup`), lalu
  - perbarui URL di ESP32 lewat `http://localhost:8080/tools/flash.html` → **Read device settings / Set WiFi**
    (ganti Server URL saja; tidak perlu flash ulang),
  - cetak/tampilkan QR baru (`docs/assets/qr_expo.png`).
- Matikan ngrok: `make expo-public-stop` (layanan Docker tetap jalan; `make down` untuk mematikan semuanya).
- Authtoken dipasang sekali per mesin: `ngrok config add-authtoken <TOKEN>` (dari dashboard.ngrok.com, di luar repo).
  ngrok dipasang tanpa sudo di `~/.local/bin` (lihat `make doctor`).

## 4. Keamanan (semua endpoint publik)

| Bagian | Perlindungan |
|---|---|
| Kiriman sensor/node (`/api/sensor/readings`, `/api/node/readings`) | `SENSOR_TOKEN` / `NODE_TOKEN` **wajib** di mode expo (header `X-Node-Token`); tanpa token yang diatur semua kiriman ditolak. `make tokens` mengisi token acak di `.env` |
| Halaman alat (`/tools/flash.html`, `/tools/recorder.html`), reset baseline, dokumentasi API | **Hanya dari komputer booth**: permintaan lewat ngrok selalu membawa `X-Forwarded-For`, nginx menolaknya (403). Akses langsung `http://localhost:8080/...` tetap jalan. Promote, rollback, impor, labeling hanya lewat `make` di terminal (tidak ada endpoint HTTP) |
| Unggah foto, sensor, push | Batas laju per pengunjung di nginx (429): unggah 10/menit, sensor 3/s, subscribe 10/menit; ukuran badan dibatasi |
| Rahasia | Hanya di `.env` (tidak di repo, tidak di respons API, tidak dicetak skrip); arsip hasil dicek bebas rahasia |

Kenapa "hanya dari komputer booth" dan bukan ADMIN_TOKEN: paling sederhana dan tidak bisa ditebak dari internet
(pengunjung lewat ngrok tidak bisa menghapus header yang ditambahkan ngrok), tanpa kata sandi baru yang harus diketik
di lab.

## 5. Kuota ngrok gratis: data dan jumlah permintaan

Batas paket gratis (periksa angka terbaru di dashboard ngrok): sekitar **1 GB data keluar** dan **20.000 permintaan
HTTP per bulan**. Yang paling cepat habis adalah **jumlah permintaan**.

| Sumber (lewat ngrok) | Permintaan per jam | Data per jam |
|---|---|---|
| ESP32 Beta, tiap 2 s (bawaan) | 1.800 | ±1 MB |
| ESP32 Beta, tiap 10 s (disarankan saat pameran) | 360 | ±0,2 MB |
| HP pengunjung di halaman Beta (polling 10 s, riwayat bertahap) | ±1.500 selama halaman terbuka | ±1–2 MB |
| Buka halaman pertama kali (Beta) | ±10 | ±0,15 MB |
| Halaman Product (model 3D ±3,5 MB) | – | buka **hanya di layar booth** (localhost) |

Saran:
- **Layar booth selalu `http://localhost:8080`** (tidak memakai kuota ngrok sama sekali).
- Saat pameran, atur interval ESP32 ke **10 s** (flash.html → Set WiFi → *Seconds between readings*).
- Satu hari pameran 8 jam dengan ESP32 10 s ≈ 2.900 permintaan + pengunjung. Bila kuota mendekati habis (dashboard
  ngrok), minta pengunjung melihat layar booth; pertimbangkan paket ngrok berbayar untuk hari H.
- Halaman yang dibuka lewat ngrok otomatis polling lebih jarang (10 s), dan riwayat sensor diambil bertahap.

## 6. Notifikasi kejadian

- Pengunjung menekan **Enable alerts** (halaman Beta) atau ikon lonceng. Izin hanya diminta saat ditekan.
- **Android (Chrome):** notifikasi masuk saat tab terbuka, di latar belakang, dan (Web Push) saat browser ditutup.
  **iPhone:** hanya setelah AirLens ditambahkan ke Home Screen (Share → Add to Home Screen, iOS 16.4+).
- Web Push butuh kunci VAPID di `.env` (`make vapid-keys`, sekali). Server hanya menyimpan subscription push.

## 7. Jalur darurat

| Masalah | Langkah |
|---|---|
| Internet putus | Layar booth tetap `http://localhost:8080`. Jalankan simulator Beta berlabel "Simulated": `python3 scripts/sensor_sim.py --replay dataset`. ESP32 terus mencoba sampai internet kembali; setelah kembali, `make expo-public` (alamat baru) dan perbarui URL ESP32 |
| ngrok putus / alamat berubah | `make expo-public`, perbarui URL ESP32 (flash.html) dan QR |
| Layanan mati / error | `make expo-setup` (ulang dari awal, aman); log: `make logs` |
| Sensor rusak / ESP32 hilang | Simulator seperti di atas (selalu berlabel "Simulated"); fitur foto → kualitas udara tetap jalan |
| ESP32 tidak terdeteksi di komputer lab | Driver USB (CP210x/CH340) butuh hak admin. Flash dan Set WiFi dari laptop saja; alamatnya ngrok, jadi sama |
| Kuota ngrok habis | Pengunjung melihat layar booth (localhost); ESP32 menunggu |
| Model hilang / salah | `make models-pull` (atau `make models-pull VERSION=n`) |
