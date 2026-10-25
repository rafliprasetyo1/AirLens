# Prompt per fase — AirLens

Cara pakai:
1. Ikuti README.md bagian A sampai distro WSL `AirLens` siap dan Claude Code terpasang di dalamnya.
2. Letakkan `CLAUDE.md`, `PROMPTS.md`, dan `README.md` di `~/AirLens`, buka folder itu lewat VS Code (ekstensi WSL),
   lalu jalankan Claude Code dari terminal VS Code yang terhubung ke distro `AirLens`.
3. Kirim prompt satu fase, tinjau hasilnya, baru lanjut. Effort yang disarankan tertulis di tiap fase.
4. Isi `.env` sendiri; jangan pernah menempelkan kunci API ke chat.

---

## Fase S — Siapkan tempat kerja di distro WSL AirLens (effort: medium; hanya di laptop)

```
Baca CLAUDE.md dan pegang sebagai aturan proyek. Kamu berjalan di distro WSL bernama AirLens (Ubuntu 24.04),
yang baru dibuat dan masih kosong. Fase S: siapkan tempat kerja. Tulis rencana dulu dan tunggu persetujuan,
karena fase ini mengubah sistem.
1. Periksa: nama distro (echo $WSL_DISTRO_NAME), versi Ubuntu, apakah systemd aktif, sisa disk, RAM, dan apakah
   perintah docker sudah tersedia. Kalau docker ada, tentukan apakah itu Docker Desktop (integrasi WSL) atau
   Docker Engine di distro ini.
2. Kalau docker belum ada: jelaskan dua pilihan (aktifkan integrasi WSL untuk distro AirLens di Docker Desktop,
   ATAU pasang Docker Engine resmi dari repositori apt Docker). Rekomendasikan satu dengan alasan dan tunggu pilihan saya.
   Kalau Docker Engine dipilih: pasang dari repositori resmi Docker, aktifkan systemd di /etc/wsl.conf bila belum,
   tambahkan pengguna ke grup docker, dan beri tahu saya kapan harus menjalankan `wsl --shutdown` dari PowerShell.
3. Pasang alat dasar: git, make, curl, ca-certificates, jq. Atur git (nama, email, line ending LF); tanyakan nama dan
   email saya, jangan menebak.
4. Pastikan proyek di ~/AirLens (bukan /mnt/c), buat .gitattributes, .gitignore awal, dan git init dengan branch main.
5. Uji: `docker run --rm hello-world` dan `docker compose version` berjalan tanpa sudo.
Kriteria selesai: semua pemeriksaan OK dengan bukti keluaran perintah, ringkasan apa yang diubah di sistem,
dan catatan di SETUP_LOG.md.
```

## Fase 0 — Cek lingkungan (effort: medium; jalankan di laptop DAN di lab)

```
Baca CLAUDE.md dan pegang sebagai aturan proyek. Fase 0: periksa lingkungan tanpa mengubah sistem.
Laporkan: nama distro, versi Ubuntu, lokasi proyek (pastikan bukan di /mnt/c), versi docker dan docker compose,
Docker Engine atau Docker Desktop, sisa ruang disk, RAM untuk WSL, dan GPU di container
(docker run --rm --gpus all <image CUDA bertag spesifik> nvidia-smi). Kalau GPU tidak terlihat, jelaskan penyebab
yang mungkin (driver Windows, NVIDIA Container Toolkit) tanpa memasangnya.
Uji apakah container bisa menjangkau LM Studio di Windows: tentukan alamat yang benar (IP gateway WSL atau mode
jaringan mirrored), tes curl ke /v1/models dari dalam container sementara, tulis alamat yang berhasil. Kalau LM Studio
tidak berjalan (misalnya di laptop), tandai sebagai "dilewati", bukan gagal.
Tulis hasilnya ke ENVIRONMENT.md dengan bagian terpisah untuk laptop dan lab, plus nilai yang harus diisi di .env.
Kriteria selesai: ENVIRONMENT.md ada, setiap pemeriksaan berstatus OK / GAGAL / DILEWATI dengan bukti keluaran perintah.
```

## Fase 1 — Kerangka proyek dan infrastruktur compose (effort: medium)

```
Fase 1: tulis rencana dulu, tunggu persetujuan, lalu kerjakan.
Buat kerangka sesuai CLAUDE.md: folder api/, web/, trainer/, scheduler/, src/airlens/ (kode bersama), config/,
data/, artifacts/, results/, tests/; .gitignore, .gitattributes, .env.example, config/laptop.yaml, config/lab.yaml,
compose.yaml (api, web, db, mlflow, scheduler, trainer dengan profil train), compose.gpu.yaml. Port host: api 8000,
web 8080, mlflow 5000; db tidak dibuka ke host. Semua image bertag spesifik, dependency terkunci, healthcheck,
restart policy, batas memori wajar untuk laptop.
Skema database dengan migrasi Alembic: predictions, iqair_readings, model_versions, monitoring_reports.
Endpoint /health di api yang mengecek koneksi db.
Makefile dengan target sesuai CLAUDE.md (target yang belum berfungsi boleh mencetak "belum tersedia, lihat Fase X").
Kriteria selesai: `make up` menaikkan semua layanan, semua healthcheck sehat, curl localhost:8000/health -> ok,
MLflow terbuka di localhost:5000, `make test` berjalan di container, README.md tetap akurat.
```

## Fase 2 — Data (effort: high; bagian paling menentukan)

```
Fase 2: tulis rencana dulu termasuk daftar dataset, ukuran unduhan, dan lisensi masing-masing; tunggu persetujuan.
Saya tidak memotret sendiri, jadi semua data dari sumber publik berlisensi jelas. Kerjakan di container trainer:
1. Skrip unduh tiap dataset dari sumber resmi dengan verifikasi checksum bila tersedia. Kredensial dari .env.
2. Normalisasi metadata ke satu skema: image_path, source, city, lat, lon, timestamp, pm25, aqi_asli, skala_asli,
   license, attribution.
3. Konversi ke kategori AQI US EPA dari PM2.5 dengan tabel breakpoint terbaru (revisi 2024). Verifikasi tabelnya,
   tulis test untuk batas tiap kategori. Kalau PM2.5 tidak ada, jelaskan cara konversi dan risikonya sebelum lanjut.
4. Deduplikasi: perceptual hash + ambang near-duplicate, termasuk frame hampir sama dari lokasi/kamera yang sama.
   Laporkan jumlah sebelum dan sesudah per dataset.
5. Filter kualitas: buang gambar malam, dalam ruangan, terlalu gelap/terang, atau rusak; laporkan jumlah per alasan.
6. Distribusi kelas per dataset dan per kota. Usulkan penggabungan kelas bila ada kelas terlalu jarang; tunggu persetujuan.
7. Split berdasarkan kota/lokasi dan waktu: train, validation, test. Satu kelompok kota disisihkan penuh untuk test.
   Test otomatis yang membuktikan tidak ada hash gambar maupun lokasi yang sama di dua split.
8. Manifest data (hash tiap file) dan data_version. DATA_CARD.md: sumber, lisensi, atribusi, jumlah, distribusi,
   keputusan pembersihan, batasan yang diketahui.
Target: `make data PROFILE=laptop` (subset kecil untuk uji alur) dan `make data PROFILE=lab` (penuh).
Kriteria selesai: manifest dan split tersimpan, semua test lulus, DATA_CARD.md lengkap, ringkasan angka ditampilkan.
```

## Fase 2b — Opsional: set uji Indonesia (effort: high)

```
Fase 2b: cek ketersediaan dulu, jangan langsung membangun pipeline penuh.
Cari stasiun pemantau PM2.5 di Indonesia lewat OpenAQ API v3 yang punya data per jam. Untuk tiap stasiun, cari foto
Mapillary API v4 dalam radius kecil (1-2 km), siang hari, luar ruangan, lalu pasangkan dengan PM2.5 OpenAQ pada jam
yang sama (toleransi waktu dicatat). Laporkan jumlah stasiun, jumlah pasangan per stasiun, dan distribusi kategori.
Kalau total di bawah 100 pasangan, laporkan dan tanyakan apakah tetap dipakai sebagai uji kecil.
Simpan lisensi dan atribusi tiap foto, khusus test (tidak pernah untuk pelatihan), deduplikasi terhadap seluruh data
latih, perbarui DATA_CARD.md.
Kriteria selesai: laporan ketersediaan, dan bila disetujui, set uji Indonesia dengan manifest dan atribusi.
```

## Fase 3 — Pelatihan, evaluasi, dan registry (effort: medium untuk kode, high untuk tinjauan akhir)

```
Fase 3: tulis rencana dulu, tunggu persetujuan.
1. Baseline: fitur kabut klasik (dark channel prior, kontras, saturasi, kecerahan, entropi) + logistic regression
   dan GBM, plus prediktor kelas mayoritas.
2. Model utama: CNN pralatih (MobileNetV3 dan EfficientNet-B0) di-fine-tune. Augmentasi aman untuk kabut (jangan
   augmentasi warna/kontras yang mengubah label). Profil laptop: subset kecil, epoch sedikit, untuk menguji alur.
   Profil lab: data penuh di GPU.
3. Kalibrasi temperature scaling di validasi. Tentukan ambang "belum pasti" di validasi.
4. Evaluasi di test (dan test Indonesia bila ada): balanced accuracy, macro-F1, recall per kelas, confusion matrix,
   ECE + reliability diagram, akurasi pada prediksi yang lolos ambang, dan persentase yang ditolak.
5. Opsional pembanding Qwen2.5-VL lewat LM Studio (VLM_BASE_URL), JSON, temperature 0, pada set test yang sama,
   dengan waktu per gambar dan perangkat. Lewati dengan rapi bila LM Studio tidak terjangkau.
6. Semua run ke MLflow (param, metrik, artefak, data_version, commit git). Model terbaik didaftarkan ke registry
   dengan alias "production". `make train PROFILE=...` dan `make eval PROFILE=...` menghasilkan
   results/eval_<tanggal>.csv dan grafik.
Lalu jalankan tinjauan terpisah: kebocoran data, ambang yang disetel di test, metrik yang menyesatkan.
Kriteria selesai: tabel perbandingan semua model, artefak di MLflow, model production terdaftar, test lulus.
```

## Fase 4 — API dan website dengan alur utama utuh (effort: medium)

```
Fase 4: tulis rencana dulu, tunggu persetujuan.
API (FastAPI):
- POST /predict menjalankan SELURUH alur utama: validasi file (tipe, ukuran, isi), hapus EXIF, pemeriksaan foto luar
  ruangan/siang/langit (heuristik; Qwen-VL hanya opsional dan tidak boleh memblokir bila mati), praproses, prediksi
  model production dari MLflow, kalibrasi, ambang "belum pasti", pembanding IQAir (cache per kota, tangani batas
  panggilan dan kegagalan), pencatatan ke db dengan versi model dan data.
- Kemajuan nyata per tahap dikirim ke frontend lewat Server-Sent Events atau endpoint status job. Tidak ada timer palsu.
- Lokasi untuk IQAir: pilihan kota oleh pengguna atau izin lokasi browser; jangan pakai GPS dari EXIF.
- Tangani semua keadaan: foto ditolak, keyakinan rendah, IQAir tidak terjangkau, model gagal dimuat.
- Test API dengan pytest (file valid, file palsu, file terlalu besar, IQAir mati).
Website (layanan web, localhost:8080):
- Dua panel: kiri unggah dan pratinjau foto, kanan hasil. Tahapan proses mengikuti status asli dari API.
- Hasil: kategori dan warna sesuai standar AQI, skor, keyakinan, pembanding IQAir dan selisih, petunjuk visual yang
  benar-benar dihitung (kontras, dark channel, kecerahan langit), saran sesuai kategori, riwayat sesi.
- Teks "perkiraan, bukan pengukuran resmi" selalu terlihat. Persetujuan eksplisit bila foto ingin disimpan.
Kriteria selesai: alur end-to-end jalan via docker compose dengan foto dari set test, semua keadaan galat tampil
benar di UI, test API lulus.
```

## Fase 4b — Animasi dan interaksi (effort: medium)

```
Fase 4b: perbagus interaksi tanpa mengubah alur utama dan tanpa menambah ketergantungan berat.
- Area seret-lepas dengan sorotan saat foto diseret di atasnya; pratinjau muncul dengan transisi halus.
- Garis pemindai di atas foto selama analisis; tiga tahap proses menyala sesuai event dari API.
- Busur skor terisi beranimasi, angka naik ke nilai akhir, warna berubah sesuai kategori.
- Kartu hasil masuk bertahap; pesan galat jelas dengan tombol coba lagi.
- Hormati prefers-reduced-motion, semua kontrol bisa dipakai dengan keyboard, fokus terlihat, kontras teks minimal
  4.5:1, nyaman di lebar 360 px, tidak ada pergeseran tata letak saat hasil muncul.
Kriteria selesai: uji manual di desktop dan lebar ponsel, uji keyboard saja, dan mode reduced motion.
```

## Fase 5 — Monitoring, retraining, shadow mode, rollback (effort: medium)

```
Fase 5: tulis rencana dulu, tunggu persetujuan.
Tidak ada label benar dari pengguna, jadi monitoring memakai sinyal yang tersedia:
1. Drift input: statistik fitur gambar (kecerahan, kontras, saturasi, dark channel) dan embedding CNN dibanding data
   latih; PSI/KS per fitur.
2. Distribusi keyakinan dan tingkat "belum pasti"/penolakan per minggu.
3. Selisih terhadap IQAir. Tulis jelas bahwa ini proksi berisik karena IQAir tingkat kota.
Layanan scheduler menjalankan job mingguan: hitung metrik, simpan ke monitoring_reports, buat laporan Markdown di
results/, beri peringatan (log + webhook opsional dari .env) bila melewati ambang di config. `make monitor` menjalankan
job yang sama secara manual.
Retraining: `make retrain` melatih ulang, mendaftarkan versi baru sebagai "challenger"; API menjalankannya dalam shadow
mode (memprediksi dan mencatat, tidak ditampilkan). `make promote` membandingkan challenger vs production pada test tetap
dan data shadow, promosi hanya bila kriteria di config terpenuhi. `make rollback` memindahkan alias production ke
versi sebelumnya tanpa build ulang.
Simulasikan drift (menggelapkan atau mengaburkan gambar test) untuk membuktikan peringatan menyala.
Kriteria selesai: job berjalan manual dan terjadwal, simulasi drift memicu peringatan, alur shadow-promosi-rollback
terbukti lewat perintah yang dijalankan.
```

## Fase 6 — Persiapan menjalankan di lab (effort: medium)

```
Fase 6: siapkan agar seluruh proyek bisa dijalankan di komputer lab dari nol.
- Pastikan README.md bagian "Menjalankan di lab" akurat terhadap kode yang sudah ada; perbaiki bila berbeda.
- `make lab-all PROFILE=lab`: cek lingkungan, unduh data, latih, evaluasi semua model (Qwen-VL bila VLM_BASE_URL
  terjangkau), lalu `make export-results` mengemas results/ dan ekspor MLflow ke satu arsip bertanggal.
- Perkirakan waktu dan ruang disk tiap langkah dari pengukuran di laptop, tulis di README.
- Uji alur ini dari klon bersih di laptop dengan PROFILE=laptop sebagai simulasi.
Kriteria selesai: klon bersih -> make lab-all PROFILE=laptop -> arsip hasil terbentuk, tanpa langkah manual tersembunyi.
```

## Fase 7 — Laporan dan presentasi (effort: low atau medium)

```
Fase 7: dari hasil di results/ dan MLflow, susun REPORT.md:
- Tabel perbandingan model (baseline, CNN, Qwen-VL bila ada): metrik, kalibrasi, waktu per gambar, perangkat.
- Diagram alur utama dan arsitektur compose.
- Siklus MLOps: data, model, deployment, monitoring, improvement, masing-masing dengan bukti dari proyek.
- Batasan yang jujur: tidak ada foto lokal dari pengguna, domain shift ke Indonesia, label kota bukan titik,
  selisih waktu label, IQAir sebagai proksi berisik, keterbatasan paket gratis.
Jangan menambah angka yang tidak ada di hasil.
Kriteria selesai: REPORT.md dan gambar pendukung siap dipindahkan ke format laporan.
```

---

## Prompt tinjauan (effort high; jalankan di akhir Fase 2, 3, dan 5)

```
Tinjau pekerjaan fase ini sebagai reviewer MLOps yang skeptis. Cari: kebocoran data antar split, duplikat yang lolos,
label yang salah konversi, ambang atau hyperparameter yang disetel di test, metrik yang menyesatkan, rahasia yang
bocor, langkah yang tidak reproducible, dan klaim tanpa bukti. Jalankan pemeriksaan nyata, bukan sekadar membaca kode.
Urutkan temuan dari yang paling berisiko dan usulkan perbaikan; jangan mengubah kode tanpa persetujuan.
```

## Prompt saat melanjutkan sesi baru

```
Baca CLAUDE.md, README.md, DECISIONS.md, dan git log 20 commit terakhir. Ringkas di fase mana proyek berada, apa yang
sudah selesai menurut kriteria fase, dan apa langkah berikutnya. Jangan mengubah apa pun sebelum saya setujui.
```
