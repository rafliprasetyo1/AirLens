> **Catatan (2026-11-22):** sebagian prompt ini digantikan oleh [7_kaggle_dua_mesin_expo.md](7_kaggle_dua_mesin_expo.md):
> pelatihan kini di Kaggle (bukan wajib di lab; `make lab-all PROFILE=lab` tetap ada sebagai cadangan), pameran
> dijalankan komputer lab, dan jaringan ngrok penuh tanpa IP lokal. `AirLens_perintah_lab.txt` sudah ditulis ulang
> untuk sesi lab tanpa pelatihan.

Kerjakan di laptop setelah prompt 1–4 selesai. Di komputer lab aku HANYA memakai terminal WSL dan menyalin perintah manual (tanpa Claude Code), dan lab hanya dipakai untuk pelatihan yang butuh GPU. Jadi semua persiapan harus beres di sini, dan perintah di lab harus sesedikit mungkin. Ada empat bagian: (I) ganti nama tiga kelas, (II) siapkan alur lab dan impor hasilnya ke laptop, (III) notifikasi masuk dari website untuk semua kejadian (Beta, node lengkap/simulator, kamera live), (IV) langkah terakhir: website bisa kubuka dan kuuji langsung dari HP lewat ngrok. Tunjukkan rencana dulu dan tunggu persetujuanku. Jangan push.

# Bagian I · Nama tiga tingkat

## Nama baru

| Kelas sekarang | Nama baru (Inggris / Indonesia) | Kategori AQI asli | Rentang AQI |
|---|---|---|---|
| moderate (good + moderate) | Low / Rendah | Good + Moderate | 0–100 |
| unhealthy (usg + unhealthy) | Elevated / Meningkat | Unhealthy for sensitive groups + Unhealthy | 101–200 |
| very_unhealthy (very unhealthy + hazardous) | High / Tinggi | Very unhealthy + Hazardous | 201+ |

Alasan: "Moderate/Sedang" sudah dipakai IQAir untuk AQI 51–100, yang di AirLens masuk "Low"; memakai kata yang sama akan membingungkan saat dibandingkan dengan baseline IQAir.

## Yang dikerjakan

1. Satu sumber kebenaran untuk skema 3 tingkat (id kelas tetap `low`, `elevated`, `high`; label tampilan Inggris dan Indonesia; rentang AQI; saran kesehatan), dipakai trainer, API, dan semua halaman web. Cari dulu di mana nama kelas dan saran kesehatan didefinisikan sekarang (`src/airlens/aqi.py`, `config/*.yaml`, `web/static/app.js`, halaman Beta) dan jangan menduplikasi.
2. Saran kesehatan: Low = aktivitas luar ruang normal; Elevated = kelompok sensitif membatasi aktivitas berat di luar ruang, yang lain mengurangi aktivitas berat yang lama; High = semua orang menghindari aktivitas luar ruang yang berat, kelompok sensitif tetap di dalam ruangan. Sesuaikan bunyinya dengan teks saran yang sudah ada agar konsisten.
3. Kompatibilitas: model lama (5 kelas dan 3 kelas dengan nama lama) tetap ditampilkan benar lewat pemetaan di metadata (`class_merge`), sehingga rollback tetap aman. `promote.py` tetap menolak promosi bila skema kelas berbeda.
4. Trainer menyimpan nama skema baru di metadata model, dan menyimpan bobot PyTorch yang dibutuhkan Grad-CAM++ (bila belum dilakukan di tahap 2).
5. Perbandingan dengan baseline IQAir di website memakai rentang AQI di atas untuk memetakan angka IQAir ke tingkat yang sama.
6. Perbarui teks di halaman web, `docs/AIRLENS_V2_DETAIL.md` (bagian 3), dan catat keputusan di DECISIONS.md.
7. Tes: pemetaan kelas lama → baru, saran kesehatan per tingkat, pemetaan AQI IQAir → tingkat (termasuk batas 100/101 dan 200/201), kompatibilitas rollback.

# Bagian II · Alur lab dan impor ke laptop

1. `make lab-all PROFILE=lab` menjalankan semuanya dalam satu perintah: cek, layanan, data (termasuk sumber `smoke`), pelatihan model AQI 3 tingkat (dengan bobot PyTorch untuk Grad-CAM++), evaluasi, perbandingan adil 5 vs 3 kelas (`compare_merge`) pada split test yang sama, **pelatihan + evaluasi + ekspor ONNX model asap `airlens-smoke`** (lihat `docs/prompts/4_konsep_utama.md` bagian C), dan terakhir ekspor hasil. Urutkan supaya model AQI 3 tingkat dan model asap (yang paling penting) selesai dan terkemas lebih dulu. Bila model 5 kelas pembanding tidak tersedia di MLflow lab, latih satu model referensi 5 kelas dengan arsitektur yang sama di dalam alur ini. Estimasikan total waktunya dari logs/lab_*/timings.tsv sesi sebelumnya (±40 menit untuk satu pelatihan) dan pastikan muat dalam ±4 jam; bila tidak muat, tunjukkan pilihan (misalnya epoch model asap dikurangi) sebelum memutuskan. Kegagalan compare_merge atau model 5 kelas referensi tidak boleh menggagalkan ekspor dua model utama. Sediakan saklar darurat lewat variabel lingkungan untuk melewati bagian yang bermasalah (misalnya melewati compare_merge), dan catat di RINGKASAN.txt bagian mana yang dilewati.
2. Hasil compare_merge (`results/compare_merge_3class.json` dan ringkasan tabel: macro-F1 keseluruhan, per sumber termasuk Dhaka, porsi "belum pasti", recall kelas High) dan metrik model asap (`results/smoke_eval.json`: F1, recall asap, presisi, confusion matrix) ikut masuk arsip ekspor dan RINGKASAN.txt.
3. `make import-results ARCHIVE=<path .tar.gz>` di laptop: memasukkan arsip hasil lab ke MLflow laptop (artefak model + riwayat run + registry), lalu mendaftarkan model 3 tingkat baru sebagai challenger `airlens` dan model asap sebagai challenger `airlens-smoke` (menggantikan model dev). Tanyakan konfirmasi sebelum menimpa data MLflow laptop, dan jelaskan di rencana apa yang tertimpa.
4. Perbarui `AirLens_perintah_lab.txt` agar sesuai alur baru. Isinya hanya perintah terminal yang disalin manual: siapkan, `make lab-all PROFILE=lab`, salin arsip ke Desktop Windows, commit results/ dan logs/ ringkas lalu push, bersihkan. Cek setiap perintah benar terhadap kode.
5. Uji di laptop sebelum push: `make lab-all PROFILE=laptop SMOKE=1` menghasilkan arsip (dengan model AQI dan model asap versi kecil), lalu `make import-results` dengan arsip itu berhasil dan kedua model muncul sebagai challenger.

# Bagian III · Notifikasi dari website untuk semua kejadian

Respons website terhadap sensor dan kamera adalah notifikasi yang masuk ke perangkat pengguna (sesuai saran dosen: tanpa LED di alat, peringatan lewat website). Sumber kejadiannya satu: trigger engine dari prompt 4 bagian A (`smoke_confirmed`, `invisible_gas`, `visible_smoke`, `back_to_normal`), yang menerima Beta, node lengkap/simulator, dan kamera live. Periksa dulu apa yang sudah dibuat dan bangun di atasnya; bila sebagian notifikasi sudah dibuat sebelumnya untuk Beta saja, sambungkan ke trigger engine, jangan membuat jalur kedua.

Dua tingkat, kerjakan berurutan:

1. **Notifikasi saat website terbuka** (wajib):
   - Tombol "Enable alerts" di halaman Beta dan Live camera (dan ikon lonceng kecil di header semua halaman). Izin notifikasi hanya diminta saat tombol ditekan, tidak otomatis saat halaman dibuka.
   - Saat ada kejadian: notifikasi sistem sesuai jenisnya (misalnya "Smoke confirmed: camera and gas sensor agree", "Invisible gas detected", "Visible smoke, check the room", "Possible local smoke or gas" untuk Beta saja) berisi sumber, nilai pemicu, dan saran singkat; ketuk notifikasi membuka halaman yang relevan (Live camera atau Beta). Pakai service worker (`registration.showNotification`), karena `new Notification()` tidak berjalan di Chrome Android.
   - Di dalam halaman: banner Alert, getar singkat (`navigator.vibrate`, bila didukung), dan bunyi pendek yang bisa dimatikan.
   - Notifikasi hanya saat kejadian baru dan satu notifikasi "Back to normal" saat pulih, memakai jeda anti-spam dari `config/triggers.yaml`. Bacaan dari simulator diberi tanda "Simulated" di teks notifikasi.
2. **Web Push saat website tertutup** (kerjakan bila tingkat 1 sudah lulus):
   - Pengguna yang menekan "Enable alerts" juga didaftarkan untuk push (subscription disimpan di tabel baru lewat migrasi alembic, bisa dihapus lewat "Disable alerts").
   - API mengirim push saat ada kejadian, memakai `pywebpush` dan kunci VAPID. Kunci dibuat lewat skrip (`make vapid-keys`) dan disimpan di `.env` (tambahkan contoh kosong di `.env.example`), tidak pernah di repo.
   - Jelaskan di halaman Beta dan EXPO.md: di Android (Chrome) push masuk walau tab ditutup; di iPhone hanya bila website ditambahkan ke Home Screen (iOS 16.4+), jadi siapkan `manifest.webmanifest` dan ikon AirLens agar bisa dipasang.
   - Subscription yang kedaluwarsa (respons 404/410) dihapus otomatis.
3. Privasi: tidak menyimpan data pribadi selain subscription push; tulis singkat di halaman Beta untuk apa izin notifikasi dipakai.
4. Tes: setiap kejadian memicu tepat satu notifikasi, jeda anti-spam, notifikasi pulih, penghapusan subscription kedaluwarsa (kirim push di-mock).

# Bagian IV · Uji langsung dari HP lewat ngrok (langkah terakhir di laptop)

Kerjakan setelah Bagian I–III selesai dan `make test` lulus. Tujuannya: aku membuka website AirLens dari HP lewat alamat HTTPS ngrok dan mencoba semua fitur, sama seperti pengunjung expo nanti.

Aturan keamanan:
- Aku sudah punya akun ngrok dan authtoken. JANGAN minta authtoken ditempel di chat, dan jangan menulisnya ke file mana pun di repo. Kalau ngrok belum terhubung ke akunku, minta aku menjalankan sendiri di terminal: `ngrok config add-authtoken <token>` (tersimpan di konfigurasi ngrok, di luar repo).
- Domain dev ngrok-ku disimpan di `.env` sebagai `NGROK_DOMAIN` (tambahkan contoh kosongnya di `.env.example`), tidak ditulis langsung di kode atau dokumen.

Yang dikerjakan:
1. Cek ngrok di WSL (`ngrok version`). Kalau belum ada, pasang lewat repo apt resmi ngrok dan tunjukkan perintahnya sebelum dijalankan. Cek versi: versi baru memakai `--url=`, versi lama `--domain=`.
2. `make expo-public`: menjalankan `make expo` (db, mlflow, api, web), menunggu semuanya sehat, lalu menjalankan `ngrok http 8080 --url=$NGROK_DOMAIN`, dan mencetak alamat publiknya dengan jelas. Bila `NGROK_DOMAIN` kosong, berhenti dengan pesan cara mengisinya. Ngrok berjalan di WSL dan meneruskan ke localhost:8080, jadi tidak perlu mirrored networking atau aturan firewall Windows untuk jalur ini. Ctrl+C mematikan ngrok dengan rapi; layanan Docker tetap jalan (sebutkan perintah untuk mematikannya).
3. Uji dari sisi laptop sebelum aku memegang HP, dan laporkan hasilnya:
   - `curl` ke `https://$NGROK_DOMAIN/` dan endpoint health API lewat ngrok (pakai header `ngrok-skip-browser-warning: 1` agar melewati halaman peringatan).
   - Unggah satu foto contoh lewat API publik dan pastikan event SSE progres (`/api/jobs/{id}/events`) benar-benar mengalir bertahap lewat ngrok, tidak tertahan sampai akhir. Bila tertahan, perbaiki konfigurasi nginx untuk lokasi SSE (misalnya `proxy_buffering off`, `X-Accel-Buffering: no`, timeout yang cukup) lalu uji ulang.
   - Grad-CAM++ foto, halaman Beta (dengan `scripts/sensor_sim.py` jalan), dan simulator node (`scripts/node_sim.py cycle`) bisa diakses lewat alamat publik; `POST /api/live/frame` merespons lewat ngrok dalam waktu wajar; SSE kejadian (`/api/events/stream`) mengalir; service worker dan manifest termuat lewat HTTPS ngrok tanpa galat.
   - Hitung kira-kira pemakaian data ngrok per menit kamera live (ukuran frame × frekuensi + respons) dan tulis di EXPO.md, karena batas paket gratis sekitar 1 GB per bulan.
   - Semua aset halaman memakai path relatif atau same-origin, sehingga tidak ada permintaan ke `localhost` dari HP dan tidak ada mixed content (http di halaman https).
4. Buat QR alamat publik (misalnya `docs/assets/qr_expo.png` dan tampilkan juga di terminal), karena domain dev ngrok tetap dan QR bisa dicetak untuk booth.
5. Beri aku daftar uji di HP yang singkat dan berurutan:
   - buka URL / pindai QR, lewati halaman peringatan ngrok sekali;
   - halaman utama: unggah foto dari kamera HP, progres berjalan, hasil tingkat Low/Elevated/High tampil, Grad-CAM++ dan slidernya bisa dipakai;
   - halaman Live camera: Start camera, izinkan, pilih kamera belakang; peta panas Grad-CAM++ bergerak mengikuti gambar; arahkan ke video asap di layar lain atau dupa, peluang asap naik dan muncul kejadian Visible smoke;
   - gabungan: jalankan simulator gas (Beta atau node `smoke`) sambil kamera live melihat asap → kejadian Smoke confirmed;
   - halaman Beta: status berpindah Warming up → Normal → Alert → Normal dari simulator, label "Simulated" terlihat;
   - notifikasi: tekan "Enable alerts", izinkan; saat simulator atau kamera memicu kejadian, notifikasi sistem masuk ke HP (sekali tab terbuka di latar belakang, sekali lagi setelah tab/browser ditutup untuk menguji Web Push), dan "Back to normal" masuk saat pulih;
   - navigasi, halaman Product, dan Build guides terbuka; tampilan rapi di layar HP;
   - matikan WiFi HP (pakai data seluler) untuk memastikan benar-benar lewat internet.
6. Perbarui `docs/EXPO.md` dengan alur `make expo-public` ini dan catatan batas paket gratis ngrok (sekitar 1 GB data keluar dan 20.000 permintaan per bulan; model 3D di halaman Product sebaiknya dibuka di layar booth saja).

## Selesai bila

`make test` lulus; halaman utama, Beta, dan Live camera menampilkan nama baru; model lama di MLflow tetap tampil benar; simulasi lab di laptop (SMOKE, dua model) dan impor arsipnya berhasil; `AirLens_perintah_lab.txt` sudah diperbarui; notifikasi semua jenis kejadian dan Back to normal masuk (termasuk Web Push saat tab tertutup); `make expo-public` berjalan dan uji dari laptop lewat alamat ngrok (termasuk SSE) lulus, lalu aku mencoba daftar uji di HP. Ringkas perubahannya, lalu tunggu aku memeriksa sebelum push.
