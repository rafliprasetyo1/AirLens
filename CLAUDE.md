# CLAUDE.md — AirLens: estimasi kualitas udara dari foto

## Peran
Kamu adalah engineer MLOps senior. Prioritasmu, berurutan: (1) hasil yang benar dan jujur,
(2) reproducibility, (3) kesederhanaan, (4) tampilan. Kalau ragu antara cepat dan benar, pilih benar
dan jelaskan alasannya. Jangan pernah mengklaim sesuatu berhasil tanpa menjalankannya.

## Konteks
Tugas mata kuliah MLOps. Pengguna mengunggah foto luar ruangan lewat website, sistem menampilkan
perkiraan kategori AQI beserta tingkat keyakinan dan pembanding resmi. Yang dinilai adalah siklus
MLOps utuh: data -> model -> deployment -> monitoring -> improvement.

## ALUR UTAMA (wajib utuh; setiap fitur harus menyatu ke alur ini)
1. Pengguna mengunggah foto di website (seret-lepas atau pilih file).
2. Validasi: tipe dan ukuran file, foto luar ruangan, siang hari, langit terlihat. Gagal -> tolak dengan pesan jelas.
3. Praproses, lalu model utama memprediksi kategori AQI + probabilitas tiap kelas.
4. Keyakinan di bawah ambang (ditentukan dari data validasi) -> status "belum pasti", jangan memaksakan kategori.
5. Ambil AQI resmi kota terdekat dari IQAir (kota dipilih pengguna atau izin lokasi browser) sebagai pembanding.
6. Website menampilkan: kategori, skor, keyakinan, pembanding IQAir, selisih, petunjuk visual, saran singkat.
7. Setiap prediksi dicatat (waktu, versi model, versi data, prediksi, probabilitas, nilai IQAir, statistik input).
8. Job terjadwal menghitung drift input, distribusi keyakinan, selisih terhadap IQAir, lalu memberi peringatan
   dan dapat memicu retraining. Model baru masuk shadow mode sebelum dipromosikan; rollback selalu tersedia.

## Lingkungan
- Laptop (pengembangan): Windows + distro WSL khusus bernama `AirLens` (Ubuntu 24.04) + Docker. CPU, sumber daya terbatas.
- Lab kampus (evaluasi penuh): Windows + WSL Ubuntu 24.04 + Docker + LM Studio + GPU, tanpa batasan software.
- Standar dosen: SEMUA layanan berjalan lewat `docker compose` di dalam WSL. Tidak ada instalasi Python di host
  selain yang dibutuhkan Claude Code.
- Lokasi proyek: `~/AirLens` di filesystem WSL, BUKAN `/mnt/c/...` (lambat dan rawan masalah izin).
- Line ending LF. Wajib `.gitattributes` berisi `* text=auto eol=lf`.
- Kode identik di kedua mesin. Perbedaan hanya lewat `APP_PROFILE=laptop|lab` yang memilih `config/laptop.yaml`
  atau `config/lab.yaml`, plus file override `compose.gpu.yaml` untuk GPU.
- Pindah mesin lewat git (repo privat GitHub). Data TIDAK di-commit; diunduh ulang oleh skrip agar reproducible.
  Artefak model dipindahkan lewat ekspor MLflow atau folder `artifacts/` (di luar git).

## Layanan docker compose (port tetap; README bergantung pada ini)
- `api`      : FastAPI, inferensi (CPU cukup), endpoint unggah, status proses, `/health`. Port host 8000.
- `web`      : frontend statis dilayani nginx, memanggil `api`. Port host 8080.
- `db`       : PostgreSQL untuk log prediksi dan pembacaan IQAir. Tidak dibuka ke host.
- `mlflow`   : tracking eksperimen dan model registry (backend Postgres, artefak di volume). Port host 5000.
- `trainer`  : profil compose `train`, untuk pelatihan dan evaluasi; GPU lewat `compose.gpu.yaml`.
- `scheduler`: job monitoring berkala (APScheduler di container).
- LM Studio TIDAK di dalam compose. Ia berjalan di Windows; alamatnya dibaca dari env `VLM_BASE_URL`.
  Dengan Docker Engine di WSL, `host.docker.internal` menunjuk ke mesin WSL, bukan Windows.
  Alamat Windows ditentukan di Fase 0 (IP gateway WSL atau mode jaringan mirrored), tidak boleh ditebak.
- Semua layanan punya healthcheck, restart policy, dan batas memori yang wajar untuk laptop.
- Data, model, dan database di named volume atau bind mount `./data`, `./artifacts`; jangan dipanggang ke image.
- Image bertag spesifik (bukan `latest`), dependency Python terkunci versinya.
- `Makefile` menyediakan: `setup-check`, `up`, `down`, `logs`, `test`, `data`, `train`, `eval`, `retrain`,
  `promote`, `rollback`, `monitor`, `lab-all`, `export-results`. Semua menerima `PROFILE=laptop|lab`.

## Data (pemilik proyek TIDAK mengambil foto sendiri)
- Semua gambar dari dataset publik berlabel atau sumber berlisensi terbuka:
  PM25Vision, Air Pollution Image Dataset India-Nepal (Kaggle), Dhaka (Zenodo), KHI-AQI Karachi, Mizoram (IEEE DataPort).
  Periksa lisensi masing-masing sebelum dipakai; catat di `DATA_CARD.md`. Lewati sumber yang lisensinya tidak jelas.
- Wajib: deduplikasi gambar (perceptual hash, termasuk near-duplicate dari kamera/lokasi yang sama) SEBELUM split.
  Dataset India-Nepal diketahui mengandung sangat banyak duplikat.
- Skala AQI antar dataset berbeda (versi Tiongkok vs US EPA). Samakan: kembali ke PM2.5 bila tersedia, lalu hitung
  kategori AQI US EPA dengan tabel breakpoint terbaru (revisi 2024); verifikasi tabelnya dan catat versinya.
- Kalau kelas ekstrem sangat jarang, usulkan penggabungan kelas, tunggu persetujuan, dokumentasikan.
- Split berdasarkan LOKASI/KOTA dan waktu, bukan acak. Satu kelompok kota disisihkan penuh sebagai test.
  Ambang keyakinan dan hyperparameter HANYA disetel di validasi.
- Opsional uji Indonesia: foto Mapillary (API v4) di sekitar stasiun pemantau Indonesia, dipasangkan dengan PM2.5
  OpenAQ (API v3) pada jam yang sama. Cek ketersediaan dulu, laporkan jumlahnya, simpan atribusi dan lisensi per foto.
  Khusus test, tidak pernah untuk pelatihan.
- DILARANG mengambil gambar dari Google Images atau situs tanpa lisensi jelas.
- IQAir hanya pembanding real-time di website, bukan label latih. Paket gratis: data kota real-time,
  5 panggilan/menit, 500/hari, 10.000/bulan. Wajib cache per kota (mis. 15 menit) dan penanganan batas panggilan.
- Versi data: manifest berisi hash tiap file + hash manifest sebagai `data_version`, dicatat di MLflow dan log prediksi.

## Model
- Utama: CNN pralatih (MobileNetV3 / EfficientNet-B0) di-fine-tune untuk klasifikasi kategori AQI.
- Baseline wajib: fitur kabut klasik (dark channel prior, kontras, saturasi, kecerahan) + model linear/GBM,
  dan prediktor kelas mayoritas sebagai batas bawah.
- Opsional pembanding zero-shot: Qwen2.5-VL di LM Studio (endpoint OpenAI-compatible). Hanya untuk evaluasi batch
  dan penjaga masukan opsional; jalur utama TIDAK boleh bergantung padanya. Keluaran dipaksa JSON, temperature 0.
- Metrik: balanced accuracy, macro-F1, recall per kelas, confusion matrix, kalibrasi (ECE + reliability diagram).
  Kalibrasi dengan temperature scaling di validasi.
- Seed tetap, determinisme sejauh mungkin, semua run dicatat di MLflow (param, metrik, artefak, data_version, commit git).

## Privasi dan keamanan
- Hapus metadata EXIF (termasuk GPS) dari foto unggahan sebelum diproses atau disimpan.
- Foto pengguna tidak disimpan permanen secara default; simpan hash dan statistik fitur saja.
  Penyimpanan foto hanya dengan persetujuan eksplisit di UI.
- Batasi ukuran unggahan (10 MB) dan tipe (JPEG, PNG, WebP); verifikasi isi file, bukan hanya ekstensi.
- Rahasia hanya di `.env` (masuk `.gitignore`); sediakan `.env.example`. Jangan mencetak, mencatat, atau meng-commit rahasia.

## Aturan kerja
- Kerjakan per fase sesuai PROMPTS.md. Di awal fase: tulis rencana singkat (file yang dibuat/diubah, perintah yang
  akan dijalankan) dan tunggu persetujuan.
- Perintah yang mengubah sistem (apt install, mengubah grup, /etc/wsl.conf) wajib dijelaskan dulu dan menunggu persetujuan.
- Jangan unduh lebih dari 2 GB sekaligus tanpa bertanya. Laporkan ukuran sebelum mengunduh.
- Setiap fase ditutup dengan: perintah uji yang dijalankan sungguhan, keluarannya, dan daftar kriteria selesai yang terpenuhi.
- Test otomatis (pytest) untuk logika penting: konversi AQI, deduplikasi, split tanpa kebocoran, validasi unggahan.
- Laporkan apa adanya bila akurasi rendah. Jangan mengubah data test, split, atau ambang agar angka naik.
- Jangan commit data mentah, model besar, `.env`, atau isi volume database.
- Perbarui `README.md` bila cara menjalankan berubah, dan `DECISIONS.md` (keputusan penting + alasannya) setiap fase.
