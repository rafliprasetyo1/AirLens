# Prompt 7: pelatihan di Kaggle, dua mesin setara, pameran di komputer lab, ngrok penuh

Ada perubahan alur dari dosen:
- Seluruh sistem harus bisa berjalan **sama baiknya di laptop maupun di komputer lab**.
- **Saat pameran, yang menjalankan sistem adalah komputer lab.**
- Pelatihan model dipindah ke **Kaggle Notebook** (GPU gratis) supaya semua model sudah final sebelum ke lab. Sesi lab hanya untuk merakit alat Beta, menguji sensor, kalibrasi, dan gladi bersih.
- Jaringan memakai **ngrok sepenuhnya, tanpa IP lokal**.

Simpan prompt ini sebagai `docs/prompts/7_kaggle_dua_mesin_expo.md`. Kerjakan setelah prompt 6 (Beta SHAP), sebelum tahap dokumentasi dan uji dari HP. Tunjukkan rencana dulu dan tunggu persetujuanku. Kerjakan bagian demi bagian sampai tesnya lulus. Jangan push.

Konteks:
- **Laptop:** tanpa GPU, RAM 8 GB, VS Code + WSL Ubuntu + Claude Code.
- **Komputer lab:** Windows + WSL Ubuntu + Docker, punya GPU. Di sana aku **hanya memakai terminal dan menyalin perintah** (tanpa Claude Code), ditambah Chrome. Anggap aku **tidak punya hak admin Windows** di komputer lab.
- **Akun:** aku punya akun Kaggle dan token API (`KAGGLE_USERNAME`, `KAGGLE_KEY` di `.env`), serta akun ngrok dengan domain dev tetap (`NGROK_DOMAIN` di `.env`; authtoken dipasang sendiri lewat `ngrok config add-authtoken`).
- **Rahasia:** jangan pernah meminta token atau kata sandi ditempel di chat, dan jangan menulisnya ke repo.

Sebelum menulis kode, baca:
- `CLAUDE.md`, `DECISIONS.md`, `Makefile`, `compose.yaml`, `config/`, `trainer/`
- skrip lab yang ada (`lab-all`, ekspor/impor hasil, `compare_merge`)
- `docs/EXPO.md`
- `docs/prompts/4_konsep_utama.md`, `5_laptop_sebelum_lab.md`, `6_beta_shap.md`
- `firmware/beta/`

## A. Pelatihan di Kaggle (dijalankan dari laptop)

1. `PROFILE=kaggle`: menjalankan trainer langsung dengan Python, **tanpa Docker**, karena Kaggle tidak mendukung Docker.
   - MLflow memakai penyimpanan berkas (`mlruns/` di `/kaggle/working`), bukan server.
   - Jalur data dari `/kaggle/input/...` dihubungkan ke struktur `data/raw/` yang dipakai trainer.
   - Isi pipeline sama dengan `make lab-all`: model AQI 3 tingkat (dengan bobot PyTorch untuk Grad-CAM++), `compare_merge` 5 vs 3 kelas (latih model 5 kelas referensi bila perlu), model asap `airlens-smoke`, evaluasi, lalu **arsip hasil dengan format yang persis sama** dengan hasil lab.
2. **Data di Kaggle.** Periksa ketersediaan setiap sumber: PM25Vision, India-Nepal, Dhaka, dataset asap, dan MultimodalGasData bila model Beta ikut dilatih di sana.
   - Utamakan dataset yang sudah ada di Kaggle (dipasang sebagai input).
   - Bila tidak ada, unduh di dalam notebook (internet aktif). Kalau terpaksa, unggah sebagai dataset Kaggle privat dari laptop. Jelaskan pilihan dan ukurannya di rencana; ingat laptop hanya 8 GB RAM.
   - Rahasia yang dibutuhkan di notebook diambil dari **Kaggle Secrets**, bukan ditulis di notebook.
3. **Notebook atau skrip kernel** di `kaggle/`: clone repo publik (commit tertentu), pasang paket, lalu jalankan pipeline. Akselerator GPU aktif, internet aktif. Simpan juga log waktu tiap tahap.
4. **Perintah laptop:**
   - `make kaggle-push`: menjalankan kernel lewat Kaggle CLI.
   - `make kaggle-status`.
   - `make kaggle-pull`: mengunduh keluaran, memeriksa kelengkapan arsip, lalu menampilkan ringkasan metrik.

   Pesan galat harus jelas, misalnya kuota GPU habis, akun belum diverifikasi nomor HP, atau dataset tidak ditemukan.
5. **Model Beta** (`airlens-beta-gas`) tetap dilatih di laptop (CPU) sesuai prompt 6, tetapi ikut dikemas di langkah B.
6. Jalur GPU lab (`make lab-all PROFILE=lab`) **tetap berfungsi** sebagai alternatif. Jangan rusak.

## B. Paket model final dan distribusi ke dua mesin

1. `make models-publish` di laptop:
   - Mengemas model final (AQI 3 tingkat, `airlens-smoke`, `airlens-beta-gas`) beserta **manifest**: nama, versi, alias tujuan (`production`), metrik utama, sumber pelatihan (kaggle/lab/laptop), commit, tanggal, dan sha256 tiap berkas.
   - Mengunggahnya sebagai versi baru **dataset Kaggle privat** `airlens-models`, dengan catatan versi.
   - Model hanya diterbitkan setelah aku menyetujui metriknya.
2. `make models-pull [VERSION=n]` di mesin mana pun:
   - Mengunduh versi tertentu (default: terbaru) dan memeriksa sha256.
   - Mengimpor ke MLflow mesin itu dan memasang alias sesuai manifest.
   - Menampilkan model yang aktif.

   Bila model dengan versi yang sama sudah ada, jangan duplikat. Perintah ini aman diulang.
3. `make import-results` dan `make import-beta-recordings` tetap berfungsi.
4. Tes: manifest, verifikasi hash (berkas rusak harus ditolak), impor berulang tidak menggandakan, dan alias terpasang benar.

## C. Kesetaraan laptop dan komputer lab

1. `make doctor` menghasilkan laporan yang sama di kedua mesin:
   - versi Docker/Compose, image yang dipakai, ruang disk;
   - kunci `.env` yang dibutuhkan sudah terisi (hanya namanya, **tanpa menampilkan nilainya**);
   - ngrok terpasang dan authtoken sudah dikonfigurasi;
   - Kaggle CLI bisa login;
   - model aktif beserta versinya;
   - hasil uji cepat.

   Setiap masalah disertai perintah perbaikannya, dalam bahasa Indonesia.
2. `make expo-setup` (satu perintah untuk komputer lab):
   - menjalankan `doctor`;
   - menjalankan `models-pull`;
   - menyalakan layanan pameran (db, mlflow, api, web);
   - menunggu semuanya sehat;
   - menjalankan `expo-public` (ngrok);
   - mencetak alamat publik, QR di terminal dan di `docs/assets/qr_expo.png`, URL sensor untuk ESP32, dan alamat halaman alat (flash/recorder).
3. Pin versi image dan paket supaya hasil di dua mesin sama. Bila ada perbedaan yang tidak bisa dihindari (misalnya GPU lab vs CPU laptop untuk inferensi), catat di `DECISIONS.md`.

## D. Ngrok sepenuhnya, tanpa IP lokal

1. **ESP32 mengirim ke `https://<NGROK_DOMAIN>/api/sensor/readings`**, alamat yang sama di laptop maupun komputer lab, jadi ESP32 cukup di-flash sekali.
   - Firmware memakai `WiFiClientSecure` dengan sertifikat akar yang benar untuk domain ngrok. Jangan memakai `setInsecure()` kecuali tidak ada cara lain; bila terpaksa, jelaskan risikonya.
   - Firmware mengirim header `ngrok-skip-browser-warning: 1` dan `X-Node-Token`.
   - URL, WiFi, dan token disimpan di NVS lewat halaman `tools/flash.html`, bukan di kode.
2. **Keamanan, karena semua endpoint kini publik lewat internet:**
   - **`SENSOR_TOKEN` dan `NODE_TOKEN` wajib** di mode expo. Endpoint sensor menolak permintaan tanpa token.
   - **Endpoint admin hanya untuk operator:** promote, rollback, reset baseline, mode labeling, impor, dan halaman alat flash/recorder. Lindungi dengan `ADMIN_TOKEN` atau batasi ke akses dari `localhost`. Pilih yang paling sederhana dan aman, lalu jelaskan.
   - **Batas laju dan ukuran** untuk `/api/live/frame`, unggah foto, dan endpoint sensor.
   - **Rahasia tidak boleh terlihat** di halaman publik maupun di respons API.
3. **Perbarui `docs/EXPO.md`:**
   - Hapus IP lokal sebagai jalur utama. Semua lewat ngrok: ESP32, HP pengunjung, layar booth.
   - Hitung kira-kira pemakaian data per jam: ESP32 setiap 2 detik + kamera live + halaman. Bandingkan dengan batas paket gratis ngrok (sekitar 1 GB keluar per bulan) dan beri saran, misalnya interval kamera live diperbesar saat ramai.
   - **Jalur darurat bila internet putus:** layar booth membuka `http://localhost:8080` dengan simulator Beta (berlabel "Simulated"); ESP32 menunggu sampai internet kembali.
4. **Proyek Wokwi** (opsional, untuk latihan tanpa alat): `wokwi/beta/diagram.json` + sketch dengan ESP32 dan empat komponen gas sensor (diberi nama MQ-2, MQ-3, MQ-7, MQ-135), mengirim ke alamat ngrok lewat jaringan Wokwi-GUEST. Tulis cara memakainya di `wokwi/README.md`, termasuk keterbatasan simulator.

## E. Daftar perintah dan dokumen

1. **Tulis ulang `AirLens_perintah_lab.txt`** untuk sesi lab baru tanpa pelatihan, khusus komputer lab, hanya perintah yang disalin:
   1. Persiapan: git config, clone/pull, `.env`.
   2. `make doctor`.
   3. `make expo-setup`.
   4. Merakit Beta mengikuti modul `merakit-node-lite.html`, lalu uji tiap sensor.
   5. Flash ESP32 lewat Chrome (`tools/flash.html`) dan simpan WiFi + URL ngrok + token.
   6. Pemanasan sensor ±30 menit.
   7. Rekam kalibrasi lewat `tools/recorder.html`.
   8. Uji ujung ke ujung: sensor → website → SHAP → notifikasi di HP.
   9. Unggah CSV ke Google Drive.
   10. Bersihkan: hapus `.env` dan kredensial.

   Tambahkan juga:
   - **Lampiran:** jalur GPU lab (`make lab-all`) sebagai cadangan bila Kaggle tidak bisa dipakai.
   - **Bagian "Kalau ESP32 tidak terdeteksi":** driver USB butuh admin; flash dari laptop saja, karena URL ngrok sama.
2. **`docs/EXPO_HARI_H.txt`:** daftar perintah hari pameran di komputer lab, mulai dari menyalakan komputer sampai membereskan, termasuk langkah darurat (internet putus, sensor rusak, layanan mati: `make expo-setup` ulang).
3. **Perbarui `README.md` dan `DECISIONS.md`:** pelatihan di Kaggle, distribusi model lewat dataset Kaggle privat, dua mesin setara, ngrok penuh, dan alasan keamanannya.
4. **Perbarui `docs/prompts/5_laptop_sebelum_lab.md`** bila ada bagian yang sudah tidak berlaku (misalnya pelatihan wajib di lab), dengan catatan singkat yang menunjuk ke prompt ini.

## Selesai bila

1. `make test` lulus, termasuk tes baru untuk manifest, models-pull, token, dan perlindungan endpoint admin.
2. `make kaggle-push` menjalankan kernel di Kaggle sampai selesai, dan `make kaggle-pull` menghasilkan arsip yang bisa diimpor (aku akan memantau kuota GPU-nya).
3. `make models-publish` lalu `make models-pull` di laptop berhasil. Simulasikan "mesin baru" dengan volume MLflow kosong untuk membuktikan alurnya sama dengan di komputer lab.
4. `make doctor` dan `make expo-setup` berjalan di laptop dan mencetak alamat ngrok + QR. Endpoint sensor menolak permintaan tanpa token; endpoint admin tidak bisa diakses dari alamat publik tanpa izin.
5. Firmware terkompilasi dengan HTTPS ke ngrok. Proyek Wokwi bisa mengirim data ke alamat ngrok dan muncul di halaman Beta.
6. `AirLens_perintah_lab.txt` dan `docs/EXPO_HARI_H.txt` sudah ditulis, dengan setiap perintah dicek terhadap kode.
7. Laporan ringkas: berkas yang berubah, cara menjalankan, dan keputusan penting. Jangan push sebelum aku memeriksa.
