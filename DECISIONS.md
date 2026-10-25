# DECISIONS — keputusan penting dan alasannya

## Fase S — tempat kerja (2026-10-24)

- **Docker Desktop (integrasi WSL), bukan Docker Engine di distro.** Docker Desktop sudah terpasang di laptop.
  Docker Engine tidak dipasang berdampingan karena keduanya akan berebut perintah `docker`.
  Konsekuensi: `host.docker.internal` dari container menunjuk ke Windows (lihat ENVIRONMENT.md).

## Fase 0 — lingkungan (2026-10-24)

- **LM Studio tetap di luar compose, sesuai CLAUDE.md.** VLM hanya pembanding zero-shot opsional, dan jalur utama
  tidak bergantung padanya. Seluruh ALUR UTAMA berjalan hanya dengan `docker compose`. Bila `VLM_BASE_URL` kosong
  atau LM Studio mati, evaluasi VLM berstatus "dilewati", bukan gagal.
  Alternatif yang ditolak: server VLM (llama.cpp/vLLM) di compose. Image dan model beberapa GB untuk fitur opsional,
  dan tidak realistis di laptop (iGPU AMD, RAM WSL 3,8 GiB).
- Laptop tanpa GPU NVIDIA. Pelatihan penuh dan evaluasi VLM dijalankan di lab.

## Fase 1 — kerangka dan infrastruktur (2026-10-24)

- **Satu `Dockerfile` multi-stage** (target `api`, `scheduler`, `trainer`, `dev`) untuk semua layanan Python.
  Base dan pengguna sama, dan duplikasi berkurang. MLflow dan web punya Dockerfile sendiri karena basisnya berbeda.
  Kode tetap di folder `api/`, `scheduler/`, `trainer/`, `src/airlens/`.
- **Penguncian dependency:** `requirements/*.in` dikompilasi menjadi `requirements/*.txt` dengan hash
  (`uv pip compile --generate-hashes`), dijalankan di container (`make lock`), dengan `--exclude-newer 2026-10-10`
  agar penguncian ulang memberi hasil sama. `dev.txt` dikunci lebih dulu dan menjadi constraint bagi api, scheduler,
  dan trainer, sehingga versi yang dites sama dengan versi yang berjalan. Instalasi memakai
  `pip install --require-hashes --no-deps`.
- **Tag image:** versi patch terbaru yang sudah berumur lebih dari 2 minggu saat dipilih:
  `python:3.12.14-slim-bookworm`, `postgres:16.14-alpine3.23`, `nginx:1.28.3-alpine3.23`.
  Image buatan sendiri bertag `airlens/<layanan>:0.1.0`.
- **Migrasi dijalankan oleh `api` saat start** (`alembic upgrade head` lalu uvicorn), sehingga tidak perlu layanan
  tambahan. `scheduler` menunggu `api` sehat, jadi skema sudah ada saat scheduler mulai.
- **Satu instance Postgres, tiga database:** `airlens` (aplikasi), `mlflow` (backend MLflow), `airlens_test` (pytest).
  Test migrasi menghapus tabel, maka `tests/conftest.py` menolak berjalan bila nama database tidak berakhiran `_test`.
- **Skema `predictions`** menyimpan `model_version` dan `data_version` sebagai teks (sesuai log yang diwajibkan),
  `is_shadow` untuk shadow mode, `status` ok/uncertain/rejected, serta hash dan statistik input. Foto tidak disimpan.
- **`/health`** menjalankan `SELECT 1` dan membalas 503 bila db tidak terjangkau, tanpa pesan error mentah
  (bisa memuat host atau kredensial).
- **Healthcheck scheduler:** file heartbeat yang hanya diperbarui bila db terjangkau. Sehat bila umurnya
  kurang dari 3× interval.
- **Layanan `tests` (profil `test`)** ditambahkan di luar daftar CLAUDE.md, khusus untuk `make test` di container.
- **Batas memori (laptop):** db 384M, mlflow 768M, api 512M, scheduler 256M, web 64M (total ~2 GB);
  trainer 1,5G (12G di lab lewat `compose.gpu.yaml`).
- **MLflow: job executor dimatikan** (`MLFLOW_SERVER_ENABLE_JOB_EXECUTION=false`). Temuan saat uji: MLflow 3.17
  menjalankan executor job GenAI (online scoring, trace archival) yang memunculkan 60–79 proses dan terkena OOM
  (exit 137) di batas 768M sekitar setiap menit. Setelah dimatikan, pemakaian stabil di ~390 MB / 12 proses tanpa
  restart. Fitur itu tidak dipakai AirLens. Batas memori tidak dinaikkan, karena itu hanya menutupi masalah.
- **MLflow `--allowed-hosts`** berisi `localhost`, `127.0.0.1`, dan `mlflow` (dengan dan tanpa port). Middleware
  keamanan MLflow 3 bawaannya hanya menerima localhost, sehingga trainer yang memanggil `http://mlflow:5000` akan
  ditolak. Host lain tetap ditolak (diuji: 403).
- **Password Postgres hanya huruf dan angka**, karena disisipkan ke URL backend MLflow. `setup-check` memeriksanya.

## Fase 2 — data (2026-10-24 s.d. 2026-10-25)

Rincian dan angka ada di DATA_CARD.md. Ringkasan keputusan:

- **Sumber:** PM25Vision, India–Nepal (hanya Biratnagar), Dhaka (test, hanya diunduh di lab). KHI-AQI dan Mizoram
  dilewati (tidak ada unduhan publik / lisensi tidak jelas).
- **Dhaka hanya di lab:** 4,5 GB dengan kecepatan Zenodo sekitar 0,15 MB/s dari laptop (sekitar 8 jam). Struktur
  arsip (`dataset2.0/<nomor>.jpg|JPG`) dan isi xlsx sudah diverifikasi di laptop, dari 11 MB pertama arsip dan xlsx
  lengkapnya. Ekstraksi penuh baru teruji di lab.
- **India–Nepal diunduh manual oleh pengguna** (browser, lalu disalin ke `data/raw/india_nepal/`) karena kredensial
  Kaggle belum ada. Skrip memakai zip yang sudah ada, memeriksa CRC, dan mencatat sha256-nya. Di lab: isi kredensial
  Kaggle atau bawa zip yang sama, lalu cocokkan sha256 dengan DATA_CARD.
- **India–Nepal: hanya Biratnagar** (pilihan A, rekomendasi Claude, disetujui pengguna). Kolom PM2.5 di 7 lokasi India
  tidak bisa dipastikan maknanya. Opsi yang ditolak: menganggapnya indeks AQI atau konsentrasi (keduanya tidak
  terverifikasi), atau membuang seluruh dataset.
- **PM25Vision:** AQI harian dibalik dengan tabel EPA 2012, dengan `label_alt` untuk analisis sensitivitas, karena
  versi tabel yang dipakai WAQI tidak terdokumentasi.
- **Dhaka:** label dari kolom NowCast (cocok dengan AQI dan sesuai paper). Baris yang tidak konsisten dibuang, karena
  ini set test.
- **Penggabungan kelas hazardous → very_unhealthy (5 kelas).** Diusulkan Claude; pengguna mendelegasikan keputusan
  ("lakukan dengan keputusan terbaik"). Alasan: hanya 36 stasiun hazardous, terlalu sedikit untuk val/test berbasis
  lokasi. Kategori asli EPA tetap tersimpan di kolom label sebelum digabung (`all_images.parquet`).
- **Kesalahan yang ditemukan dan diperbaiki selama Fase 2:**
  - subset laptop awalnya mengambil persentase foto per stasiun, sehingga kelas good tersisa 1 foto; diganti dengan
    mengambil 10% stasiun beserta semua fotonya;
  - heuristik langit pertama salah menolak sekitar 18% foto; diganti dengan porsi piksel mirip-langit, dikalibrasi
    visual;
  - split acak membuat hazardous menumpuk di val; diganti dengan penempatan kelompok terstratifikasi.
- **Unduhan bisa dilanjutkan** (HTTP Range, hingga 20 percobaan), karena koneksi laptop sering terputus.
- **Ambang dedup** (pHash/dHash 4/6 global, 10/12 untuk lokasi yang sama) dan kualitas disetel dengan memeriksa grid
  di `results/data/<profil>/`.

## Fase 3 — model (2026-10-25)

- **Pelatihan sungguhan dijalankan di lab (GPU)** atas usul pengguna. Di laptop hanya dijalankan **uji asap**
  (`make train SMOKE=1`: MobileNetV3 saja, 1 epoch) untuk membuktikan alurnya dan menghasilkan bundle model untuk
  pengembangan Fase 4. Hasil uji asap diberi tag `smoke=true` di MLflow dan file berakhiran `_smoke`; angkanya
  **bukan** hasil evaluasi.
- **PyTorch 2.14.1**: varian `cpu` (laptop) dan `cu126` (lab, lewat `compose.gpu.yaml`), dikunci terpisah dengan hash.
  CUDA 12.6 dipilih karena wheel cu128 hanya tersedia sampai torch 2.11. Wheel diunduh dari index PyTorch;
  `--require-hashes` menjamin isinya sama dengan yang dikunci.
- **Augmentasi hanya geometris** (random resized crop 0,7–1, flip). Tanpa warna/kontras/blur karena itu mengubah
  label kabut; tanpa rotasi karena sudut hitamnya mengubah dark channel.
- **Preprocessing inferensi: resize utuh ke 224×224 tanpa center crop**, agar langit (petunjuk utama) tidak terpotong.
  Satu implementasi (`airlens.models.preprocess`, numpy + PIL) dipakai evaluasi dan API.
- **Model production = CNN (ONNX) dengan macro-F1 validasi tertinggi.** Baseline (sklearn) tidak bisa di-deploy ke API
  ONNX. Bila baseline lebih baik di validasi, hal itu dicatat dan dilaporkan; production tetap CNN terbaik.
  Pada uji asap, logreg memang lebih tinggi di validasi (0,36 vs 0,18 setelah 1 epoch), tetapi di test turun ke 0,15.
  Itu tanda validasi laptop (170 gambar) terlalu kecil untuk memilih hyperparameter dengan andal.
- **Evaluasi CNN lewat ONNX** (bukan PyTorch), jadi yang diukur sama persis dengan yang dipakai API. Ekspor diverifikasi
  (selisih logit maks 5,7e-6). Exporter ONNX lama (TorchScript) sudah deprecated di torch 2.14 tetapi masih berfungsi;
  pindah ke exporter baru adalah pekerjaan lanjutan.
- **Ambang "belum pasti"**: keyakinan terkecil yang membuat akurasi prediksi yang lolos ≥ 70% di validasi (minimal
  15/30 prediksi diterima untuk laptop/lab). Bila target tidak tercapai, ambang dengan akurasi tertinggi dipakai dan
  `target_tercapai=false` dilaporkan. Pada uji asap target tidak tercapai (model 1 epoch).
- **Tanpa commit git**, run dilacak lewat `code_version` (sha256 isi `src/`, `trainer/`, `config/`, `requirements/`) dan
  `git_commit=belum-ada-commit-dirty`.
- **Image build tahan koneksi lambat**: timeout pip 120 detik, 10 kali percobaan ulang, dan cache wheel BuildKit yang
  dipakai bersama antar tahap.
- Uji asap juga menunjukkan **set test Biratnagar (satu kamera) diprediksi buruk oleh semua model**. Ini indikasi
  pergeseran domain; diperhatikan saat evaluasi penuh di lab.

## Fase 4 dan 4b — API dan website (2026-10-25)

- **Pola job + Server-Sent Events.** `POST /predict` langsung membalas `job_id` (202); pipeline berjalan di thread
  latar. Setiap tahap (periksa → analisis → iqair → selesai) mengirim event saat **benar-benar** terjadi;
  `GET /jobs/{id}/events` mengalirkannya (nginx tanpa buffering untuk rute ini). Tidak ada timer palsu.
  Penyimpanan job di memori cukup karena uvicorn berjalan dengan 1 worker (dicatat sebagai batasan skala).
- **Model API = `airlens-aqi@production` dari MLflow**, diunduh ke volume `modelcache` per versi. API tetap hidup bila
  MLflow/model tidak ada (`/health` → `model: unavailable`, UI menampilkan pesan) dan mencoba ulang tiap 30 detik.
  API juga memeriksa alias secara berkala dan **memuat ulang otomatis bila alias berpindah versi**, sebagai dasar
  promote/rollback di Fase 5. Bila MLflow mati, versi terakhir di cache tetap dipakai.
- **Inferensi API: onnxruntime di CPU, tanpa PyTorch**, dengan preprocessing yang sama dengan evaluasi
  (`airlens.models.preprocess`).
- **Validasi unggahan:** batas 10 MB (nginx dan API); tipe dari **isi file** (PIL), bukan ekstensi; hanya
  JPEG/PNG/WebP; batas 40 MP (decompression bomb). **EXIF termasuk GPS dibuang** dengan menyalin piksel ke gambar baru;
  orientasi EXIF diterapkan lebih dulu. Lokasi untuk IQAir hanya dari pilihan kota atau izin lokasi browser.
- **Foto hanya disimpan dengan persetujuan** (centang eksplisit) ke volume `uploads`, sebagai JPEG tanpa metadata. Tanpa
  persetujuan, yang dicatat hanya sha256 piksel dan statistik. Kolom `predictions.photo_stored` mencatatnya.
- **"Skor" = rentang indeks AQI kategori** (mis. 151–200), bukan satu angka indeks. Model memprediksi kategori, jadi
  satu angka indeks akan menjadi presisi palsu. Busur di UI menunjukkan **keyakinan**.
- **Status "belum pasti"** bila keyakinan < ambang dari validasi: kategori tidak dipaksakan; UI menampilkan kandidat
  teratas sebagai keterangan, dan selisih terhadap IQAir tidak dihitung.
- **IQAir:** cache 15 menit per kota di tabel `iqair_readings` (bertahan setelah restart); kuota 5/menit dan 500/hari
  dihitung dari tabel baru `iqair_requests` (semua panggilan, termasuk yang gagal); lokasi browser dipetakan ke kota
  terdekat lewat `nearest_city`. Semua kegagalan menjadi status "tidak tersedia" dan tidak memblokir prediksi.
- **Daftar kota diverifikasi langsung ke API IQAir** (`config/cities_id.yaml`, 15 kota). Malang dan Makassar tidak
  dikenali IQAir sehingga tidak dimasukkan; pengguna di sana bisa memakai lokasi perangkat.
- **Petunjuk visual dihitung sungguhan** (kontras RMS, dark channel, kecerahan langit) dengan fungsi yang sama di
  trainer dan API (`hint_values`), lalu dibandingkan dengan kuantil data latih yang disimpan di metadata model.
- **Warna kategori = warna resmi AQI EPA.** Teks di atasnya dipilih agar kontras ≥ 4,5:1 (teks gelap di atas
  hijau/kuning/oranye/merah, putih di atas ungu/marun).
- **Frontend tanpa framework dan tanpa build step** (HTML/CSS/JS statis di nginx). Semua data server dirender lewat
  `textContent` (tanpa `innerHTML`). Riwayat sesi di `sessionStorage`.
- **Uji UI otomatis** (`make ui-test`) dengan Chrome headless (Puppeteer, image `zenika/alpine-chrome`, hanya alat
  uji dan tidak masuk compose). Keadaan "model tidak tersedia" dan "server 503" diuji dengan respons API yang
  disimulasikan (intersepsi permintaan); keadaan lain memakai API sungguhan.
- **Kesalahan selama Fase 4:**
  - Dua uji asap sempat berjalan bersamaan sehingga model v3 dilatih dengan kode lama (terlacak lewat `code_version`);
    dijalankan ulang satu kali.
  - Struktur unduhan artefak MLflow sempat ditebak; diganti dengan path yang dikembalikan MLflow.
  - onnx 1.23 menulis IR 14, sedangkan onnxruntime 1.31 menerima maksimal 13; model mini di test diberi IR 10.
    Model CNN asli tidak terdampak karena exporter PyTorch menulis IR lebih rendah.
- **Kritik desain (skill `design:design-critique`), disetujui pengguna dan diterapkan:** alur ponsel (gulir ke panel tahap
  saat analisis dimulai, header ringkas, probabilitas bertumpuk), petunjuk visual dengan satu skala "tingkat kabut"
  (persentil dibalik untuk kontras), status "belum pasti" bernada amber dengan ikon, pesan pengganti untuk pratinjau
  rusak, panel unggah lengket di desktop, dan bobot judul eksplisit. Garis pemindai tetap mengikuti durasi analisis
  yang sebenarnya (~0,1 detik) dan **tidak diperlambat buatan**.
- **Bug yang ditemukan uji UI dan diperbaiki:** `display: grid` milik komponen mengalahkan atribut `hidden`, sehingga
  kotak galat dan kartu kosong tampil sejak awal. Beberapa pemeriksaan "terlihat" sempat lulus palsu; uji sekarang
  memakai gaya terhitung. Juga: tinggi `select` 40 px (kini ≥ 44 px), dan input file `display: none` diganti
  `sr-only` agar pemilih file terbuka lewat keyboard.

## Fase 5 — monitoring, retraining, shadow mode, rollback (2026-10-25)

- **Monitoring tanpa label**, sinyal yang tersedia: (1) drift input, yaitu 7 fitur gambar dan proyeksi PCA (8 komponen)
  dari **embedding CNN**, dibanding sampel data latih model production; (2) keyakinan serta porsi "belum pasti" dan
  "ditolak", juga per minggu; (3) selisih kategori terhadap IQAir, ditulis jelas sebagai **proksi berisik** (IQAir
  tingkat kota); (4) kesepakatan challenger vs production pada data shadow.
- **ONNX diekspor dengan dua keluaran** (`logits`, `embedding` = fitur hasil pooling sebelum kepala klasifikasi).
  Referensi drift (`monitoring_reference`) disimpan di metadata model saat pelatihan.
- **Satu fungsi tanda tangan input** (`airlens.monitoring.signature.input_signature`) dipakai trainer dan API, dengan
  decode gambar penuh di kedua sisi. Mode draft JPEG (decode diperkecil) kini hanya dipakai untuk augmentasi latih;
  validasi, evaluasi, referensi, dan API memakai decode penuh. Sebelumnya perbedaan decode ini akan terbaca sebagai
  drift palsu.
- **Aturan peringatan drift: PSI terkoreksi bias ≥ 0,1 DAN KS p < 0,01, minimal 50 sampel.** PSI terkoreksi = PSI
  − (k−1)(1/n + 1/m); jumlah bin k menyesuaikan ukuran sampel. Diukur dengan simulasi 8 fitur tanpa drift:
  | Aturan | alarm palsu n=40 | n=60 | n=150 | deteksi geser 0,6 sd (n=60) |
  |---|---:|---:|---:|---:|
  | PSI mentah > 0,2 (rancangan awal) | 39% | 36% | 0% | – |
  | PSI terkoreksi > 0,2 | 16% | 6% | 0% | 85% |
  | **PSI terkoreksi ≥ 0,1 dan KS p < 0,01 (dipakai)** | 7% | 4% | 0% | 94% |
  Rancangan awal akan menyalakan alarm palsu di lebih dari sepertiga laporan mingguan dengan trafik kecil.
- **Job terjadwal**: APScheduler di layanan `scheduler`, cron dari `config monitoring.schedule` (Senin 02:00 UTC).
  `MONITOR_EVERY_MINUTES` mengganti jadwal dengan interval menit untuk pembuktian. `make monitor` menjalankan fungsi
  yang sama di container yang sama. Hasilnya: baris `monitoring_reports`, laporan Markdown
  `results/monitoring/`, dan peringatan ke log plus webhook opsional `MONITOR_WEBHOOK_URL`.
- **Scheduler TIDAK menjalankan pelatihan sendiri.** Itu butuh akses Docker socket, yang setara akses root ke host.
  "Memicu retraining" diwujudkan sebagai `retrain_triggered` di `monitoring_reports` dan rekomendasi di laporan;
  `make retrain` dijalankan manusia.
- **Shadow mode**: `make retrain` mendaftarkan versi baru dengan alias `challenger`. API memuat challenger
  (alias diperiksa berkala), memprediksi foto yang sama, dan mencatatnya dengan `is_shadow=true`. Hasilnya tidak
  pernah dikirim ke pengguna, dan galat challenger hanya masuk log.
- **Promosi** (`make promote`): challenger vs production pada **test tetap** (ONNX, temperatur dan ambang masing-masing)
  dan data shadow. Kriteria di config (`promotion`): macro-F1 tidak turun, ECE tidak naik > 0,02, sampel shadow
  minimal, dan porsi "belum pasti" di shadow tidak naik > 0,10. Ada juga syarat test tetap = data challenger (tanpa
  kebocoran). Keputusan dan alasannya ditulis ke `results/promotion_<waktu>.md`.
- **Rollback** (`make rollback [VERSION=n]`): memindahkan alias production tanpa build ulang; API memuat ulang sendiri.
  Riwayat di tabel `model_versions` (stage, `promoted_at`). Versi yang ditarik ditandai `rolled_back` agar rollback
  berikutnya mundur ke versi lebih lama, bukan bolak-balik ke versi yang baru ditarik.
- **Bug yang ditemukan test di fase ini:** pembungkus ekspor ONNX berada di mode train; setelah ekspor PyTorch
  mengembalikan mode itu dan **memindahkan model asli ke mode train** (dropout/BatchNorm aktif). Diperbaiki dengan
  `.eval()` pada pembungkus dan model.
- **Bukti alur di laptop (2026-10-25):**
  - `make drift-sim`: gelombang normal 0 peringatan drift, gelombang bergeser 6.
  - Job terjadwal berjalan sendiri (laporan #6); `make monitor` menghasilkan laporan #7.
  - `make retrain` mendaftarkan v6 sebagai challenger; 12 foto dicatat ganda (production v5 + shadow v6) tanpa
    hasil shadow di respons.
  - `make promote`: v5 → v6, API berpindah dalam ~2 detik. `make rollback`: v6 → v5, API kembali dalam ~18 detik.
- **v5 dan v6 identik persis** (data, kode, dan seed sama → pelatihan deterministik). Dengan `min_macro_f1_gain: 0.0`
  seri lolos, sehingga promosi di laptop hanya membuktikan alur. **Profil lab memakai `min_macro_f1_gain: 0.01`**:
  challenger harus lebih baik secara nyata.
- **Simulasi drift: Biratnagar bukan kontrol normal.** Pemeriksaan menunjukkan foto test Biratnagar (satu kamera) bergeser
  di 15/15 fitur dibanding data latih, sedangkan foto test PM25Vision bergeser di 0/7 fitur gambar. Kontrol normal
  simulasi memakai PM25Vision; Biratnagar dijadikan gelombang "domain baru".
- **Embedding dinilai sebagai satu kesatuan** (peringatan bila ≥ 50% komponen PCA bergeser). Per komponen, lokasi
  PM25Vision yang belum pernah dilihat sudah menyalakan 2–3 dari 8 komponen. Di produksi, setiap foto pengguna
  Indonesia adalah lokasi baru, jadi aturan per komponen akan menyalakan alarm setiap minggu.
