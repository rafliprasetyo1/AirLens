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

## Fase 6 — persiapan lab (2026-11-13)

- **Sesi lab tanpa Claude Code dan VS Code**: pengguna hanya memakai terminal Ubuntu dan menyalin perintah dari
  `AirLens_perintah_lab.txt`, sampai `git push` hasil. File itu ditulis ulang agar setiap perintahnya cocok dengan kode.
- **`make lab-all`** (`scripts/lab_all.sh`): setup-check → db+mlflow → data → train → eval → export. Durasi, status,
  dan pemakaian disk tiap tahap dicatat ke `logs/lab_<waktu>_<profil>/timings.tsv` dan `RINGKASAN.txt`. Bila satu
  tahap gagal, tahap berikutnya dilewati, tetapi **export tetap dijalankan** agar hasil parsial tidak hilang.
  `SKIP_CHECK=1` melewati setup-check (mis. GPU tidak terdeteksi tetapi tetap ingin berjalan di CPU).
- **`make export-results`** (`scripts/export_results.sh`): satu arsip `results/airlens_results_<profil>_<waktu>.tar.gz`
  berisi results/, bundle model, log, ringkasan data (report, manifest, data_version), **volume `mlartifacts`**,
  **dump database `mlflow` dan `airlens`**, info lingkungan tanpa rahasia, dan `MANIFEST.sha256`. Sebelum dikemas,
  arsip diperiksa agar tidak memuat nilai rahasia dari `.env`. Arsip dibawa lewat Google Drive/flash disk, bukan git.
- **setup-check memakai image CUDA 12.6** (sama dengan trainer `cu126`). Sebelumnya CUDA 12.8 bisa memberi "GPU
  GAGAL" palsu pada driver yang hanya mendukung 12.6. Ditambah cek alat (`make`, `git`, `curl`, `openssl`), disk
  (lab ≥ 40 GB), dan RAM.
- **VLM di lab dibatasi 300 foto test** (sampel tetap dengan seed; model production dinilai pada sampel yang sama).
  Seluruh test lab (~3.000 foto × 1–5 detik) bisa memakan berjam-jam, melebihi satu sesi lab.
- **Jalur darurat `AIRLENS_DATA_SOURCES`** (mis. `pm25vision,india_nepal`) bila unduhan Dhaka dari Zenodo terlalu
  lambat. Dari laptop terukur ~0,15 MB/s, sekitar 8 jam untuk 4,5 GB. Sumber yang dipakai tercatat di `report.json`
  dan MLflow, jadi set test tanpa Dhaka tidak tersembunyi. File perintah lab mengukur kecepatan Zenodo dulu.
- **Yang di-push dari lab hanya ringkasan kecil**: `results/eval_<tanggal>.csv`, grafik, `data_report_lab.json`, serta
  `timings.tsv` dan `RINGKASAN.txt`. Log tahap lengkap dan arsip `.tar.gz` diabaikan git.

## Halaman produk: konsep utama + Beta (2026-11-21)

- **`web/static/product.html`**: scrollytelling berbahasa Inggris, 14 bagian, mengikuti `docs/prompts/1_halaman_produk.md`
  dan `docs/AIRLENS_KONSEP_UTAMA.md`. Menggantikan versi awal (ESP32 + PMS5003 + 3 MQ, casing v0.2) yang tidak pernah
  di-commit; kerangka, gaya, dan vendor dipakai ulang. Tautan "Product" di header `index.html`.
- **Tanpa build dan tanpa CDN saat runtime** (booth bisa offline): three.js 0.160.0 (GLTFLoader, RoomEnvironment,
  BufferGeometryUtils) dan font @fontsource 5.1.0 di `web/static/vendor/` (versi, sumber, sha256 di `vendor/README.md`).
- **Model = dua GLB rakitan** (`airlens_node_concept.glb`, `airlens_beta.glb`, total ±1,2 MB) dengan node datar di root.
  Halaman mengelompokkan node per awalan nama (`enclosure_*`, `comp_<modul>__*`, `beta_case_*`) ke Group dengan titik
  putar di pusat kotak batasnya; material dikloning per kelompok agar peredupan satu modul tidak ikut ke modul lain.
  Warna dikonversi sRGB → linear karena trimesh menulis nilai sRGB ke `baseColorFactor`.
- **Label konsep selalu terlihat**: penanda "Full version · concept design" di atas kanvas (berganti "Running at this
  booth" di bagian Beta), di hero, dan di footer.
- **Sorotan** menarik modul (atau satu set: Pi 5 + AI HAT+, CO-B4 + ADS1115) ke titik di depan menara, casing 10%,
  modul lain 25%, dengan 2–3 label penunjuk. Titik label dan ujung kabel dihitung dari koordinat lokal di
  `build_concept_components.py` lewat transformasi di `assemble.py`, lalu disimpan di `product/parts.js`.
- **Kabel** digambar sebagai tabung: oranye 3,3 V, hitam GND, biru SDA, kuning SCL, hijau WE, ungu AE; rute lewat celah
  grommet sekat ganda (dari `enclosure_concept.py`). Pin dan rute ilustratif. Saat modul ditarik keluar, titik rute di
  dekatnya menyatu agar tidak ada lengkungan panjang; kabel ISB–ADS1115 menjadi lurus bila keduanya ditarik.
- **Zona termal** memakai oranye tipis untuk zona atas sesuai prompt; aliran udara Pi digambar putih keabu-abuan agar
  oranye tetap jarang (penutup lensa dan zona panas saja).
- **Contoh SHAP** hanya urutan faktor dari dokumen (CO-B4, kamera, VOC, PM2.5, baseline kota), berlabel "Example",
  tanpa angka besaran karena dokumen tidak memberinya.
- **Beta Wrapped/Unwrapped**: gulir membuka tutup bertahap; tombol (`aria-pressed`, keyboard) menimpa progres gulir
  sampai pengunjung keluar dari bagian Beta. Tanpa WebGL, tombol menukar gambar diam `beta_wrapped/unwrapped.png`.
- **Tautan ke halaman berikutnya** (`live.html`, `beta.html`, `modules/`) dipasang dengan alamat final; halamannya
  dibuat di tahap 2–3.
- **Tata letak**: berdampingan (teks kiri, model kanan) untuk desktop dan HP/tablet miring ≥ 600 px; model di atas dan
  teks di bawah untuk HP tegak. Satu media query yang sama di CSS dan JS. Teks yang tidak muat ikut bergulir biasa;
  label penunjuk tidak masuk area teks dan disembunyikan bila tidak muat.
- **Fallback**: tanpa WebGL halaman menjadi dokumen biasa dengan gambar `concept_*.png` (three.js tidak diunduh);
  `prefers-reduced-motion` langsung menampilkan keadaan akhir tiap bagian tanpa animasi berkelanjutan.
- **Pengecekan di laptop**: `python3 -m http.server` dari `web/static` + Chrome headless (puppeteer-core) untuk desktop,
  enam ukuran HP tegak/miring, reduced motion, tanpa WebGL, keyboard, tombol Beta, dan request ke domain luar.

## Tahap 2: Beta, navigasi, Grad-CAM++, mode expo (2026-11-21)

- **Sensor Beta di API** (`api/airlens_api/sensor.py`, `sensor_routes.py`, migrasi `0003`): tabel `sensor_readings`
  (sesuai prompt) ditambah `sensor_nodes` untuk baseline, status, dan hitungan histeresis per node, agar
  `POST /sensor/baseline/reset` dan "dua kali berturut-turut" tidak hilang saat API restart. Satu transaksi per bacaan
  dengan kunci baris node (`SELECT … FOR UPDATE`). Logika status berupa fungsi murni yang dites terpisah.
- **Nilai ≤ 0 disimpan, `valid=false`**, dan tidak dipakai untuk baseline maupun status. **Uptime mundur = ESP32 menyala
  ulang**: pemanas MQ dingin, jadi pemanasan dan baseline diulang (tambahan di luar prompt, dicatat di EXPO.md).
- **Token**: bila `SENSOR_TOKEN` diisi, `POST /sensor/readings` dan `POST /sensor/baseline/reset` wajib membawa
  `X-Node-Token`; endpoint GET selalu terbuka untuk halaman Beta. Halaman Beta tidak punya tombol reset karena bisa
  dibuka publik lewat ngrok.
- **Bug yang ditemukan tes**: kiriman berisi `NaN` ditolak validasi, tetapi handler 422 bawaan FastAPI ikut memuat `NaN`
  ke JSON respons sehingga server membalas 500. Handler 422 kini mengganti angka tak hingga/NaN dengan teks; respons 422
  lain tidak berubah.
- **Simulator** `scripts/sensor_sim.py` hanya memakai pustaka standar (tanpa instalasi di host). Rumus sinyalnya fungsi
  murni yang dites, termasuk uji ujung ke ujung lewat logika server: Warming up → Normal → Alert → Normal.
- **Navigasi**: markup header ditulis di tiap halaman (tanpa build), gaya bersama di `web/static/shared/nav.css` yang
  mengikuti warna halaman lewat variabel. Label sama di semua halaman (Photo demo, Beta sensor, Product, Build guides),
  termasuk halaman utama yang tetap berbahasa Indonesia. Di layar ≤ 420 px logo disembunyikan agar keempat menu muat.
- **Modul perakitan** disalin ke `web/static/modules/` oleh `scripts/sync_modules.sh` (`make sync-modules`) dengan
  satu perubahan: tautan Google Fonts dihapus, sehingga website tidak meminta apa pun ke domain luar dan tetap rapi saat
  offline. Sumbernya tetap `docs/modules/`; folder `arsip/` tidak disalin.
- **Grad-CAM++ memakai bobot PyTorch**, karena ONNX Runtime tidak punya autograd. Trainer kini mengirim `model.pt` ke
  MLflow (`bundle/model.pt`); API mengunduhnya bersama ONNX, membangun model dengan `cnn.build_model(arch,
  pretrained=False)`, dan menghitung Grad-CAM++ pada `model.features` untuk **kelas prediksi ONNX** (argmax PyTorch
  dicek sama). Model yang terdaftar sebelum perubahan ini tidak punya `model.pt`: API menampilkan "Penjelasan belum
  tersedia untuk versi model ini" sampai model dilatih ulang (Tahap 4 di lab).
- **Endpoint terpisah `GET /jobs/{id}/gradcam`** agar prediksi tetap secepat sebelumnya. Masukan ter-praproses disimpan
  di memori job selama 15 menit lalu dibuang; peta panas (grid 56 × 56) diwarnai di browser dan tidak pernah disimpan.
  Model PyTorch dipanaskan di latar saat model aktif, supaya permintaan pertama tidak menanggung impor torch (±10 s).
- **Batas memori**: torch menambah ±320 MB, dengan puncak terukur ±500 MB. Batas container `api` dinaikkan 768 → 1280 MB
  (risiko OOM saat foto besar) dan `tests` 512 → 1280 MB (tes Grad-CAM++ di 512 MB berjalan 2–12 s karena swap; tanpa
  batas: 0,43 s EfficientNet-B0, 0,19 s MobileNetV3). Total layanan expo ±2,5 GB, di bawah RAM WSL 3,9 GB.
  `cnn.py` kini mengimpor scikit-learn di dalam fungsi latih, agar API bisa memakai `build_model` tanpa scikit-learn.
- **IQAir saat internet putus**: hanya untuk galat jaringan, API memakai bacaan terakhir yang tersimpan untuk kota itu
  (berapa pun umurnya), ditandai `stale` beserta waktu pengambilannya; tanpa data tersimpan muncul pesan jelas. Galat
  lain (kuota, kunci kosong, kota tak dikenal) tidak berubah.
- **`make expo`** menyalakan `db`, `mlflow`, `api`, `web` dengan `--wait`, lalu mencetak alamat booth, LAN, dan URL ESP32.
  Docker kini berjalan langsung di WSL (bukan Docker Desktop), dan WSL laptop ini dalam mode NAT, sehingga HP/ESP32 tidak
  bisa menjangkau port 8080. Skrip mendeteksinya (`wslinfo --networking-mode`), mengambil IP Wi-Fi Windows lewat
  PowerShell, dan memberi peringatan dengan langkah mode mirrored + aturan firewall Hyper-V (`docs/EXPO.md`).
- **Kamera Beta (ESP32-CAM) dikerjakan di Tahap 3**, bersama jalur Live camera, karena butuh model asap yang baru dibuat
  di tahap itu. Beta tetap ESP32 DevKit + MQ-2; ESP32-CAM menjadi papan kedua (ADC2 ESP32-CAM tidak bisa dipakai
  bersamaan dengan WiFi).
- **Ngrok = jalur akses utama** (keputusan pengguna, 2026-11-21), bukan opsional: ponsel pengunjung dan uji dari HP
  memakai alamat HTTPS ngrok dengan domain dev tetap (QR dicetak lebih dulu; HTTPS juga wajib untuk kamera di browser).
  Akses LAN (mode mirrored WSL + firewall) hanya cadangan saat internet booth putus dan jalur ESP32 ke laptop.
  `docs/EXPO.md` disusun ulang; `make expo-public` dan uji SSE lewat ngrok dikerjakan di Tahap 6.

## Tahap 3: trigger engine, node lengkap (simulasi), model asap, Live camera, kamera Beta (2026-11-21)

- **Satu trigger engine untuk semua sumber** (`api/airlens_api/triggers.py`, aturan di `config/triggers.yaml`). Node
  lengkap, simulator, Beta MQ-2, kamera Beta, dan kamera live hanya mengirim angka; keputusan kejadian diambil di satu
  tempat. Ambang alert Beta dipindah dari `config/laptop.yaml`/`lab.yaml` ke `triggers.yaml` (bagian `beta`), supaya
  tidak ada dua sumber kebenaran. Profil kini hanya berisi pemanasan, baseline, dan batas offline sensor.
- **Kamera**: median smoke_prob ≥ 0,70 pada 3 dari 5 penilaian terakhir untuk masuk, < 0,40 selama 30 s untuk keluar.
  Median + "3 dari 5" meredam satu frame keliru; histeresis mencegah kedip. **Gas** (CO ppm, indeks VOC/NOx Sensirion)
  memakai ambang masuk/keluar + jumlah bacaan berturut-turut. Beta MQ-2 memakai status alert yang sudah ber-histeresis.
- **Empat kejadian**: smoke_confirmed (kamera + gas, high), invisible_gas (gas saja, high), visible_smoke (kamera saja,
  medium), back_to_normal (info, sekali saat semua pemicu keluar). Satu ruangan (`booth`) menggabungkan sumber lewat pola
  nama (`node:*`, `beta:*`, `betacam:*`, `live:*`). Jeda anti-spam 60 s per jenis; sumber yang diam > 60 s dianggap
  keluar (alat mati tidak boleh mengunci alarm).
- **smoke_confirmed tidak turun** ke visible_smoke/invisible_gas saat asap mereda (salah satu pemicu keluar lebih dulu).
  Tanpa aturan ini siklus simulator memunculkan "Gas detected" palsu setelah asap terkonfirmasi. Kejadian berikutnya
  setelah smoke_confirmed selalu back_to_normal.
- **Kejadian disimpan** (tabel `events`, migrasi 0004) dan disiarkan lewat SSE `/api/events/stream` (nginx tanpa
  buffering). Thread pemanggil (route sinkron) menyiarkan ke loop asyncio lewat `call_soon_threadsafe`. Kejadian yang
  melibatkan sumber simulasi diberi `simulated: true` dan label "Simulated" di website. Uji langsung
  `node_sim.py cycle` lewat nginx menghasilkan urutan yang diharapkan:
  visible_smoke → smoke_confirmed → back_to_normal → invisible_gas → back_to_normal → visible_smoke → back_to_normal.
- **Node lengkap belum ada fisiknya**: `POST /api/node/readings` (skema hardware/README.md, rentang nilai divalidasi,
  tabel `node_readings`, migrasi 0005) diisi `scripts/node_sim.py` (stdlib, skenario normal/smoke/invisible_gas/
  visible_smoke/cycle). Di website ditulis "Full version (concept): simulated node".
- **Model asap terpisah dari model AQI**: registry `airlens-smoke` dengan alias production/challenger sendiri,
  `make train-smoke`, `promote-smoke` (F1 asap tidak turun dan recall asap turun ≤ 0,02, karena asap yang terlewat
  lebih berbahaya dari alarm palsu), `rollback-smoke`. Tanpa shadow mode dan monitoring mingguan; itu khusus model AQI.
  Fungsi registry diberi parameter `model`; perilaku untuk AQI tidak berubah.
- **Data asap: D-Fire (CC0 1.0)**, mirror Kaggle `sayedgamal99/smoke-fire-detection-yolo` yang punya `data.yaml`
  (names `[smoke, fire]`, indeks kelas dibaca dari situ, bukan ditebak). Label YOLO → biner: ada kotak asap = smoke,
  tanpa kotak/berkas label = no_smoke, **hanya api = dibuang** (asap mungkin ada tapi tidak dilabeli; label ambigu
  lebih buruk daripada data lebih sedikit). Split asli dataset dipertahankan; duplikat lintas split (pHash/dHash)
  dibuang dari val/test, train dipertahankan. Laptop mengunduh subset berkas per berkas (320/80/100), bukan zip 3,1 GB.
  Panggilan Kaggle diberi percobaan ulang dan daftar berkas di-cache, karena listing pernah putus di tengah.
- **Augmentasi untuk kamera dalam ruangan**: kecerahan/kontras/saturasi, blur ringan, crop 0,6–1,0. Arsitektur
  EfficientNet-B0 lewat `cnn.train_cnn` yang sama dengan model AQI (ditambah parameter `train_tf`).
- **Live camera** (`/live.html`, `POST /api/live/frame`): browser mengirim JPEG ±320 px kira-kira tiap 1 s, dan frame
  berikutnya baru dikirim setelah respons datang. Server membatasi 300 KB / sisi 640 px, satu frame dalam satu waktu
  (429 bila sibuk) dan 0,5 s per sesi. Interval di browser melambat sendiri bila server lambat atau menjawab 429.
  Grad-CAM++ dihitung untuk **kelas smoke** (bukan kelas prediksi), karena pertanyaannya "bagian mana yang membuat model
  mengira ada asap"; grid 28 × 28 cukup untuk overlay ±320 px dan dua kali lebih ringan dari 56 × 56. Frame tidak pernah
  ditulis ke disk atau database. Kamera berhenti saat tab disembunyikan. Badge "Dev model" tampil selama model berasal
  dari laptop.
- **Kamera Beta (ESP32-CAM)**: `POST /api/beta/camera/frame` dengan badan JPEG mentah (paling mudah dari ESP32-CAM),
  token sama dengan Beta MQ-2 (`SENSOR_TOKEN`), sumber `betacam:<node>`. **Frame tidak ditampilkan secara default**
  (`BETA_CAMERA_SHOW_FRAMES=false`): halaman Beta hanya menampilkan angka. Bila diisi true, hanya frame terakhir yang
  ditahan di memori (untuk ditampilkan beserta peta panas), tidak pernah disimpan. `scripts/beta_cam_sim.py` (stdlib)
  mengirim gambar test D-Fire sesuai label; ukuran dibaca dari header JPEG agar tidak butuh Pillow di host.
- **Banner kejadian bersama** (`shared/events.js`) di halaman Beta dan Live: keadaan awal dari `/api/events/latest`,
  lalu SSE; koneksi ditutup saat tab tersembunyi. Notifikasi sistem dan Web Push menyusul di Tahap 4.
- **ModelStore** kini menerima nama model dan env bundle lokal (`SMOKE_BUNDLE_DIR` untuk tes), cache model asap di
  subfolder `smoke/` agar nomor versi kedua registry tidak bertabrakan.
- **Model asap dev (laptop, `airlens-smoke` v1, 1+1 epoch CPU, 296 gambar latih)**: test 85 gambar F1 asap 0,687,
  recall 0,657, presisi 0,719, AP 0,72 (val F1 0,780). Median smoke_prob gambar asap test hanya 0,55, dan hanya 6/35
  yang ≥ 0,70, sehingga pemicu kamera jarang menyala dengan model ini. Ambang pemicu **tidak** diturunkan agar angka
  terlihat bagus; model final dilatih di Kaggle (prompt 7). Uji ujung-ke-ujung `smoke_confirmed` (kamera live palsu
  di Chrome + `node_sim.py invisible_gas`) memakai 6 gambar asap yang dikenali model, karena yang diuji adalah
  mekanisme dua pemicu, bukan akurasi.
- **Perubahan rencana (2026-11-21, prompt 7)**: pelatihan dipindah ke Kaggle, pameran dijalankan komputer lab, jaringan
  ngrok penuh tanpa IP lokal. Token sensor yang di tahap ini masih opsional akan diwajibkan di mode expo.

## Revisi Beta SHAP (prompt 6, 2026-11-21)

- **Permintaan dosen**: Beta harus punya SHAP. Agar SHAP bermakna (lebih dari satu fitur), Beta memakai empat MQ
  (MQ-2/3/7/135 di GPIO34/35/32/33, hanya ADC1 karena ADC2 mati saat WiFi) dan model AI kecil. Adaptor 5 V 2 A
  karena empat pemanas ±600 mA.
- **Dataset publik, bukan rekaman sendiri**: alat hanya ada di lab, jadi model dilatih dengan MultimodalGasData
  (Mendeley `zkwgkjkjn9` v2, CC BY 4.0; hanya CSV 330 KB, sha256 diperiksa). Sumber `beta_gas` di `make data`.
- **Temuan dataset yang menentukan desain** (DATA_CARD §7): satu sesi berurutan per kelas → split per blok waktu
  (10 blok, pola train/val/test, purge 15 baris) alih-alih acak; drift di dalam sesi; asap MENURUNKAN nilai (searah
  Rs) → fitur alat = **Rs/R0** (bukan rasio mV); MQ-3 hampir tidak bereaksi pada parfum. Asumsi arah Rs belum terbukti
  di alat kita; rekaman kalibrasi lab yang akan membuktikannya.
- **Fitur**: rasio empat sensor + satu turunan MQ-3/MQ-2 (alkohol relatif terhadap asap), tetap mudah dijelaskan.
  Urutan baris tidak dipakai sebagai fitur waktu.
- **Model LightGBM** (bukan RandomForest/XGBoost): ringan, deterministik, dan TreeSHAP persisnya bawaan
  (`pred_contrib`), sehingga API tidak memuat pustaka `shap`/`numba`. `shap.TreeExplainer` di trainer dipakai untuk
  plot global dan pemeriksaan silang (selisih 0,0); additivity diperiksa saat latih (selisih 5e-15). Hasil test:
  macro-F1 0,865 (asap 0,995, campuran 0,995, udara bersih 0,731, alkohol 0,738); aturan MQ-2 lama 0,10 karena rasio
  MQ-2 asap di dataset hanya ±0,8 (> ambang 0,6). Satu sesi per kelas berarti angka ini batas atas.
- **Temuan replay** (`sensor_sim.py --replay dataset`): pada udara bersih model kadang menebak alkohol (0,89–0,93) dan
  memicu alert; SHAP memperlihatkan dorongan terbesar dari MQ-7 1,12–1,17× (drift sesi NoGas). Ambang tidak disetel
  ulang dengan data uji; ini dicatat sebagai batasan dan menjadi alasan utama rekaman kalibrasi di lab.
- **Registry `airlens-beta-gas` terpisah**: production/challenger sendiri, `make promote-beta` (macro-F1 tidak turun,
  recall asap turun ≤ 0,02), `make rollback-beta`; challenger dihitung diam-diam per bacaan di API (kolom
  `challenger_class`, shadow). Alur challenger → promote → rollback sudah dijalankan di laptop.
- **Pemicu**: keputusan Beta pindah ke model (peluang asap/alkohol ≥ 0,70 dua kali → alert; keluar saat clean_air
  ≥ 0,60), ambang di `config/triggers.yaml`. Tanpa model, aturan rasio MQ-2 lama dipakai (format lama juga tetap
  diterima). Pesan kejadian memuat kalimat alasan dari 2–3 SHAP positif terbesar.
- **SHAP disimpan per bacaan** (kolom JSONB `shap`, migrasi 0006) agar endpoint explain dan waterfall tidak menghitung
  ulang, dan supaya penjelasan yang tampil adalah penjelasan bacaan yang memicu keputusan.
- **Firmware HTTPS ke ngrok** (sekalian prompt 7): `WiFiClientSecure` dengan akar Let's Encrypt ISRG Root X1, X2, YE
  (rantai `*.ngrok-free.app`/`.dev` diperiksa: YE2 → Root YE → X2 → X1), jam NTP sebelum TLS, koneksi keep-alive,
  header `ngrok-skip-browser-warning` dan `X-Node-Token`, pengaturan di NVS lewat Serial. Tidak ada `setInsecure()`.
  `arduino-cli` 1.3.1 + core esp32 3.3.13 dipasang di `~/.local` tanpa sudo (unduhan ±1,46 GB, lebih besar dari
  perkiraan 1 GB karena toolchain semua varian chip). `.bin` gabungan dipangkas dari 4 MB ke ±1,1–1,2 MB dan di-commit
  agar komputer lab cukup membuka `tools/flash.html` (esptool-js 0.7.0 lokal).
- **ESP32-CAM** mengirim JPEG QVGA tiap 5 s (bukan 2 s) untuk menghemat kuota ngrok (±7 MB/jam).
- **Proyek Wokwi** memakai sketch identik dengan firmware (dicek tes), dengan pembagi 10k/20k seperti alat asli.
- **Ditunda ke prompt 7**: `AirLens_perintah_lab.txt` (ditulis ulang untuk sesi lab tanpa pelatihan) dan perlindungan
  admin untuk halaman alat flash/recorder.

## Tahap 4 bagian I: nama tiga tingkat (2026-11-22)

- **Low / Elevated / High** (Rendah / Meningkat / Tinggi; AQI 0–100, 101–200, 201+), id `low`/`elevated`/`high`,
  menggantikan nama gabungan EPA. Alasan: "Moderate/Sedang" dipakai IQAir untuk AQI 51–100, yang di AirLens masuk
  Low; kata yang sama membingungkan saat dibandingkan. Satu sumber kebenaran `src/airlens/tiers.py`.
- **Saran kesehatan** per tingkat mengikuti teks lama yang sudah ada (gaya bahasa sama), disatukan per tingkat.
  Warna: hijau EPA untuk Low, oranye USG untuk Elevated, ungu Very unhealthy untuk High (teks kontras ≥ 4,5:1).
- **Kompatibilitas tanpa menulis ulang data**: `dataset.parquet` lama berlabel moderate/unhealthy/very_unhealthy;
  `load_dataset` mengganti nama itu ke tingkat (artinya identik), sehingga `data_version` tetap dan model lama tetap
  bisa dibandingkan. `make data` berikutnya menulis nama baru. Model lama ditampilkan lewat `tier_of` (nama lama 3 kelas
  → tingkat); model 5 kelas tetap kategori EPA. Diverifikasi langsung: production `airlens-aqi` v1 (nama lama) tampil
  Rendah/Meningkat/Tinggi.
- **promote.py** menyamakan nama lama dan baru sebelum membandingkan skema (`normalize_classes`), agar model tiga
  tingkat baru bisa menggantikan model lama berskema sama; skema yang benar-benar berbeda (5 vs 3) tetap ditolak.
- Metadata model baru memuat `class_scheme: airlens-3tier-v1`.

## Tahap 4 bagian II–III: lab-all, import-results, notifikasi (2026-11-22)

- **lab-all** mendahulukan dua model utama: data → AQI tiga tingkat → model asap → evaluasi → **kemas** (arsip pertama),
  baru tahap opsional (referensi 5 kelas + compare_merge) dan kemas ulang. Tahap opsional tidak pernah menggagalkan
  alur. Saklar darurat: `SKIP_CHECK`, `SKIP_SMOKE_MODEL`, `SKIP_COMPARE`, `SKIP_SMOKE_DATA`, `SKIP_BETA_DATA`;
  bagian yang dilewati/gagal tercatat di RINGKASAN.txt (ditulis sebelum setiap kemas agar ikut masuk arsip).
- **Model referensi 5 kelas**: dataset lama hanya menyimpan label gabungan, jadi data pipeline kini juga menyimpan
  `label_epa` dan `load_dataset` menurunkan label dari situ. `make train TRAIN_CLASS_SCHEME=epa5 TRAIN_MODELS=<arsitektur
  production>` melatihnya di folder terpisah (`reference_epa5/`), mendaftar tanpa alias, tidak menimpa candidates.json.
  compare_merge kini juga melaporkan porsi "belum pasti" dan recall kelas terburuk (High), plus tabel .md.
- **import-results tidak menimpa MLflow laptop**: database lab (mlflow_db.sql) tidak dipulihkan karena akan menimpa
  riwayat laptop. Bundle model dicatat sebagai run baru (eksperimen `airlens-import`, tag sumber arsip) dan didaftarkan
  sebagai challenger `airlens-aqi` / `airlens-smoke`; production tidak disentuh. Pemindahan alias challenger yang sudah
  ada butuh konfirmasi (CONFIRM=1 atau pertanyaan interaktif). Arsip diverifikasi MANIFEST.sha256, diekstrak aman
  (`filter="data"`), dan bundle yang sha256-nya sudah diimpor tidak didaftarkan ulang. Karena data_version lab ≠
  laptop, `make promote` di laptop akan menolak (benar); pakai `make rollback VERSION=n` atau `make models-pull`.
- **Notifikasi satu jalur**: teks notifikasi dibuat server dari kejadian trigger engine (`push.notification`) dan
  ikut di payload SSE, sehingga halaman dan Web Push memakai teks yang sama. Ditampilkan lewat service worker
  (`registration.showNotification`, karena `new Notification()` tidak jalan di Chrome Android) dengan `tag` per kejadian
  agar notifikasi halaman dan push tidak dobel. Saat alerts aktif, SSE tetap terbuka di tab latar belakang.
- **Web Push**: pywebpush 2.5.0 + kunci VAPID P-256 dari `make vapid-keys` (ditulis ke .env, tidak dicetak, tidak
  menimpa kunci yang ada); kirim di thread latar agar trigger engine tidak menunggu jaringan; 404/410 menghapus
  subscription. VAPID_SUBJECT bawaan `mailto:airlens@example.com` (bukan alamat pribadi).
- **Manifest + ikon** (192/512, latar penuh agar aman sebagai maskable) supaya bisa dipasang di Home Screen iPhone,
  syarat Web Push di iOS.

## Prompt 7: Kaggle, dua mesin setara, pameran di komputer lab, ngrok penuh (2026-11-22)

- **Pelatihan di Kaggle Notebook**, tanpa Docker: profil `kaggle` (= lab), `AIRLENS_DB=none` (registry hanya alias
  MLflow; catatan riwayat DB dilewati lewat objek null), MLflow **SQLite** (file store MLflow 3 sudah dibekukan).
  Kode dikirim sebagai dataset privat `<user>/airlens-code` dari working tree laptop (commit + tanda dirty di
  CODE_INFO.json), karena commit laptop belum di-push dan kernel tidak boleh bergantung pada push. India-Nepal dan
  D-Fire dipasang sebagai **input kernel** (tanpa kredensial di notebook; pembaca zip/folder + symlink ke data/raw),
  PM25Vision dan Dhaka diunduh di dalam kernel. Arsip `airlens_results_kaggle_*.tar.gz` berformat sama dengan lab
  (MANIFEST.sha256; `mlflow.tar.gz` menggantikan dump Postgres), dibaca `make import-results` apa adanya.
- **Kaggle CLI 2.x** membaca token format baru (`KGAT_…`) dari `KAGGLE_API_TOKEN`; compose meneruskan `KAGGLE_KEY`
  ke variabel itu. Galat umum (verifikasi HP, kuota GPU, kredensial, dataset tidak ada) diterjemahkan ke pesan jelas.
- **Tidak ada pelatihan di laptop** (keputusan pemilik, setelah uji SMOKE lokal memakan waktu berjam-jam): verifikasi
  lewat tes unit dengan model sintetis; galat kernel diperbaiki dari log Kaggle.
- **Distribusi model** lewat dataset Kaggle privat `airlens-models`: paket berisi ONNX (+ berkas bobot eksternal
  `*.data`) atau LightGBM, metadata, `model.pt`, plot, dan manifest (sha256 tiap berkas, metrik, sumber, commit).
  Unggah hanya dengan `MODELS_APPROVED=1`. `models-pull` menolak paket bila satu berkas saja tidak cocok, mendaftarkan
  versi dengan tag `package_sha` (impor ulang tidak menggandakan), dan memasang alias sesuai manifest. Diuji pada
  MLflow kosong (simulasi mesin baru) dan API memuat modelnya.
- **ngrok free: alamat acak per sesi** (keputusan pemilik): `make expo-public` menjalankan ngrok di latar, membaca
  alamat dari API lokal ngrok, lalu menyimpan/menimpa `NGROK_DOMAIN` di `.env`. Konsekuensi: URL ESP32 diperbarui per
  sesi lewat flash.html (Set WiFi, tanpa flash ulang) dan QR dibuat ulang. ngrok dipasang di `~/.local/bin` tanpa sudo.
- **Keamanan**: mode expo (`EXPO_MODE=1`, diatur `expo-setup`) mewajibkan SENSOR_TOKEN/NODE_TOKEN (`make tokens`).
  Halaman alat, reset baseline, dan dokumentasi API **hanya dari komputer booth**: nginx menolak permintaan yang
  membawa `X-Forwarded-For` (selalu diisi ngrok). Dipilih karena paling sederhana dan tidak bisa dipalsukan dari
  internet, tanpa ADMIN_TOKEN baru. Batas laju per pengunjung (kunci = IP pertama di X-Forwarded-For).
  Diverifikasi lewat ngrok: 401 tanpa token, 403 alat operator, 429 saat beruntun.
- **Kuota ngrok gratis** (±1 GB keluar, ±20.000 permintaan/bulan): jumlah permintaan yang paling cepat habis.
  Riwayat sensor kini bertahap (`since`), halaman lewat ngrok polling 10 s (localhost 3 s), kamera live 1 frame/2 s
  lewat ngrok, interval ESP32 bisa diatur (firmware 1.1.0, `interval` di NVS; disarankan 10 s saat pameran), dan layar
  booth selalu localhost. Perhitungan lengkap di docs/EXPO.md.
- **make doctor / expo-setup** sama di kedua mesin; doctor tidak pernah mencetak nilai rahasia, setiap masalah
  disertai perintah perbaikan. Perbedaan yang tidak bisa dihindari: inferensi API di CPU pada kedua mesin (GPU lab
  hanya untuk pelatihan cadangan), jadi hasil inferensi sama.

## Pembersihan lingkup (2026-11-22) — menggantikan bagian terkait di atas

Lingkup ditegaskan pemilik: **proyek utama** = foto pengguna → tingkat kualitas udara dengan IQAir sebagai pembanding;
**tambahan** = alat IoT AirLens Beta (ESP32 + 4 MQ) dengan model gas dan SHAP. Akibatnya:

- **Dihapus:** Live camera (`/live.html`, `/api/live/*`), model asap `airlens-smoke` beserta data D-Fire dan target
  make-nya, kamera Beta ESP32-CAM (endpoint, firmware, simulator), dan **Grad-CAM++** (endpoint, UI di halaman foto,
  ekspor `model.pt`). PyTorch keluar dari image API (memori API kembali 768 MB). Catatan Tahap 2–3 tentang fitur-fitur
  itu di atas kini hanya sejarah.
- **XAI = SHAP saja**, hanya untuk alat Beta, karena hanya di sana parameternya bermakna (sensor). Foto tidak memakai
  SHAP (masukan piksel) maupun Grad-CAM; halaman foto menampilkan petunjuk visual fitur kabut sebagai pengukuran.
- **Kelas alkohol hanya ditampilkan**, tidak memicu peringatan (`alcohol_classes: []` di triggers.yaml): di dataset
  latih MQ-3 hampir tidak bereaksi pada parfum, sehingga peringatan alkohol palsu muncul pada udara bersih.
- **Semua pelatihan di Kaggle**, termasuk model gas Beta (dulu di laptop). Rekaman kalibrasi alat diunggah sebagai
  dataset privat (`make beta-recordings-push`); kernel melatih ulang dengan dataset publik + rekaman dan memakai model
  gabungan bila lebih baik. Di laptop `make import-beta-recordings` hanya mengevaluasi domain shift.
- **Konsep versi lengkap** (Raspberry Pi, halaman produk 3D, video, simulator node) dibiarkan apa adanya, tidak dirawat,
  dan tidak menjadi syarat tes atau layanan.
- **Kernel Kaggle v1 gagal** di tahap data karena `unar` tidak ada di image Kaggle (pelatihan belum sempat berjalan);
  kernel kini memasangnya, dan rantai model foto serta model Beta dipisah agar satu kegagalan tidak menggagalkan yang lain.
- Riwayat commit lokal yang belum di-push dibatalkan (`git reset --soft origin/main`) dan dibuat ulang lebih ringkas.

## Perombakan tampilan website (2026-11-22)

| Keputusan | Alasan |
|---|---|
| Satu tema untuk semua halaman (`web/static/shared/theme.css`): latar abu kebiruan `#E6EBED`, tinta slate `#18262E`, satu warna aksi petrol `#0A5C78` | Sebelumnya halaman Foto terang dan halaman lain gelap. Warna terang lain hanya untuk data (tingkat AQI resmi, peringatan), jadi warna selalu berarti "udara". Menghindari pola template gelap + satu aksen neon |
| Satu keluarga huruf, Archivo variabel (lebar 62–125 %), disimpan lokal (90 KB) | Judul lebar dan tebal seperti cetakan panel alat ukur, isi lebar normal, label sedikit dipadatkan. Menggantikan Space Grotesk + Inter + font sistem (tiga gaya berbeda). Lokal agar booth tetap rapi saat internet putus |
| Halaman Foto: lembar hasil dengan garis pemisah, bukan tumpukan kartu; bidang hasil diwarnai warna resmi AQI dari API | Satu hal yang mencolok per halaman. ID elemen tetap sama, jadi `app.js` dan uji UI tidak berubah perilakunya |
| Halaman Product kini tentang AirLens Beta (bukan konsep versi lengkap) | Beta yang benar-benar dipamerkan. Konsep versi lengkap tetap di panduan dan `hardware/`, tidak dimuat halaman Product |
| Model 3D modul dibangun di browser (`product/parts/`), bukan balok GLB | ESP32 DevKit V1 (WROOM-32 berpelindung beretsa, antena meander, micro-USB, EN/BOOT, CP2102, AMS1117, 30 pin bersolder), modul MQ FC-22 (jaring baja ganda, cincin crimp, trimpot 3296, LM393 di bawah), breadboard 400 lubang, resistor dengan gelang warna asli, kabel dupont. Ukuran asli dalam mm; tekstur digambar di kanvas sehingga tidak ada unduhan tekstur |
| Casing dari STL cetak asli (`hardware/enclosure-beta/stl/`) + gzip di nginx | Casing di layar sama dengan yang dicetak. Gzip: STL 329 KB -> 55 KB, three.js ±1,3 MB -> ±300 KB (hemat kuota ngrok) |
| Tata letak ESP32 di breadboard mengikuti kenyataan: baris pin di b dan j, baris a sisi GPIO terbuka | DevKit V1 menutup semua lubang breadboard kecuali satu baris; kabel GPIO 34/35/32/33 masuk ke baris itu |
| Warna garis sensor di grafik Beta = warna kabel sinyal di model 3D (MQ-2 biru, MQ-3 kuning tua, MQ-7 ungu, MQ-135 hijau) | Pengunjung bisa mencocokkan grafik dengan kabel di model |
| Tema diganti gelap atas permintaan pemilik (2026-11-22 malam): latar biru tua `#0B1424`, kepala/kaki hitam `#05080D`, aksi kuningan pucat `#D9B872` | Latar terang terasa belum selesai bagi pemilik. Kuningan senada dengan pin emas ESP32 di model 3D; tidak memakai cyan/glow. Semua teks tetap >= 4.5:1 (uji UI 39/39). Warna garis sensor dicerahkan untuk latar gelap |

## Casing Beta revisi USB dan ventilasi (2026-11-22, belum dicetak)

| Keputusan | Alasan |
|---|---|
| Breadboard + ESP32 digeser 15 mm ke dinding -X (`BB_X = -29`), celah USB 14 × 11 mm dipusatkan ke port | Sebelumnya mulut micro-USB terbenam ±18 mm dari dinding; logam colokan hanya ±6,5 mm, kabel tidak bisa masuk |
| Ruang ESP32 diberi jalur udara sendiri: kisi tegak rendah di kedua sisi (masuk) + kisi pendek di tutup (keluar); celah kabel di sekat disumbat busa | ESP32 + AMS1117 ±0,4–0,8 W tanpa jalan keluar selain celah sekat ke ruang sensor; panasnya bisa memengaruhi bacaan MQ. Juga tampilan tidak lagi timpang |
| Tulisan "AirLens Beta" di tutup diukir 0,6 mm, bukan timbul | Tutup dicetak terbalik (permukaan atas di bed) tanpa support |
