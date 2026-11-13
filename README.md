# AirLens

Perkiraan kualitas udara (kategori AQI) dari foto luar ruangan, dibangun dengan siklus MLOps lengkap:
data → model → deployment → monitoring → improvement. Semua layanan berjalan lewat `docker compose` di WSL.

> Perkiraan dari foto bersifat indikatif, bukan pengukuran resmi.

Dokumen ini punya empat bagian:

- **A.** Setup pertama kali di laptop (sekali saja)
- **B.** Kerja sehari-hari di laptop
- **C.** Menjalankan di lab komputer kampus
- **D.** Pemecahan masalah

Berkas pendamping: `CLAUDE.md` (aturan proyek untuk Claude Code) dan `PROMPTS.md` (prompt per fase).

---

## Ringkasan layanan

| Layanan | Alamat dari browser Windows | Fungsi |
|---|---|---|
| `web` | http://localhost:8080 | Website unggah foto |
| `api` | http://localhost:8000/health | FastAPI, inferensi |
| `mlflow` | http://localhost:5000 | Riwayat eksperimen dan registry model |
| `db` | (tidak dibuka) | PostgreSQL |
| `trainer` | (profil `train`) | Pelatihan dan evaluasi |
| `scheduler` | (latar belakang) | Monitoring mingguan |

Perintah `make` di README ini baru tersedia setelah fase yang disebutkan selesai.

---

## A. Setup pertama kali di laptop

Kamu akan membuat distro WSL khusus bernama **AirLens**, sehingga proyek ini terpisah dari proyek PA dan
distro Ubuntu yang sudah ada.

### A1. Perbarui WSL (PowerShell)

Buka **PowerShell** (bukan terminal Ubuntu):

```powershell
wsl --update
wsl --version
wsl -l -v
```

`wsl -l -v` menampilkan distro yang sudah ada. Pastikan belum ada distro bernama `AirLens`.

### A2. (Disarankan) Batasi memori WSL

Supaya laptop tidak kehabisan RAM saat Docker berjalan, buat atau sunting `C:\Users\<nama>\.wslconfig`:

```ini
[wsl2]
memory=6GB
processors=4
```

Sesuaikan dengan RAM laptopmu (sekitar setengahnya). Pengaturan ini berlaku untuk semua distro WSL.
Terapkan dengan `wsl --shutdown` di PowerShell.

### A3. Buat distro AirLens (PowerShell)

```powershell
wsl --install Ubuntu-24.04 --name AirLens
```

Saat pertama kali terbuka, buat **username** dan **password** Linux. Simpan password-nya; dibutuhkan untuk `sudo`.

Kalau opsi `--name` ditolak, WSL-mu belum cukup baru: ulangi `wsl --update`. Kalau tetap tidak bisa, pakai
distro Ubuntu yang sudah ada dan cukup buat folder `~/AirLens` di sana; semua langkah berikutnya tetap sama.

Masuk ke distro kapan pun dengan:

```powershell
wsl -d AirLens
```

### A4. Pasang Claude Code di dalam distro AirLens

Di terminal **AirLens** (prompt Linux, bukan PowerShell):

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

Tutup lalu buka lagi terminal, kemudian:

```bash
claude --version
claude doctor
```

Kalau `claude` tidak ditemukan, folder instalasinya belum masuk PATH; jalankan `source ~/.bashrc` atau buka
terminal baru. Login dilakukan saat pertama menjalankan `claude` (perlu paket Pro atau di atasnya).

### A5. Buat folder proyek dan salin berkas

Simpan `CLAUDE.md`, `PROMPTS.md`, dan `README.md` ke folder Downloads di Windows, lalu di terminal AirLens:

```bash
mkdir -p ~/AirLens
cp /mnt/c/Users/<nama-windows>/Downloads/{CLAUDE.md,PROMPTS.md,README.md} ~/AirLens/
cd ~/AirLens && ls
```

Proyek harus berada di `~/AirLens`, bukan di `/mnt/c/...`.

### A6. Buka di VS Code

1. Di Windows, pasang VS Code dan ekstensi **WSL** (Microsoft).
2. Dari terminal AirLens: `cd ~/AirLens && code .`
   Kalau `code` tidak dikenali: buka VS Code → `Ctrl+Shift+P` → **WSL: Connect to WSL using Distro** → pilih
   **AirLens** → **File → Open Folder** → `/home/<username>/AirLens`.
3. Pojok kiri bawah VS Code harus bertuliskan **WSL: AirLens**.
4. Pasang ekstensi **Claude Code** di jendela itu (terpasang di sisi WSL).

### A7. Siapkan Docker dan alat dasar lewat Claude Code (Fase S)

Buka terminal di VS Code (yang terhubung ke AirLens), jalankan `claude`, lalu kirim prompt **Fase S** dari
`PROMPTS.md`. Claude Code akan memeriksa sistem, mengusulkan cara memasang Docker, dan menunggu persetujuanmu.

Dua kemungkinan:

- **Kamu memakai Docker Desktop di Windows:** buka Docker Desktop → **Settings → Resources → WSL integration** →
  aktifkan **AirLens** → **Apply & restart**.
- **Tidak ada Docker Desktop:** Claude Code memasang Docker Engine resmi di dalam distro AirLens. Setelah selesai,
  jalankan `wsl --shutdown` di PowerShell lalu buka AirLens lagi, sesuai arahan Claude.

Uji:

```bash
docker run --rm hello-world
docker compose version
```

Keduanya harus berjalan **tanpa** `sudo`.

### A8. Buat repo GitHub privat

Repo dibutuhkan untuk memindahkan proyek ke komputer lab.

1. Di github.com, buat repo **privat** bernama `AirLens` tanpa README.
2. Di terminal AirLens:

```bash
cd ~/AirLens
git add .
git commit -m "Inisialisasi proyek AirLens"
git branch -M main
git remote add origin https://github.com/<username-github>/AirLens.git
git push -u origin main
```

Saat diminta password, gunakan **Personal Access Token** GitHub (bukan password akun). Data, model, dan `.env`
tidak pernah ikut di-commit.

### A9. Siapkan akun dan kunci API

| Layanan | Untuk | Wajib |
|---|---|---|
| IQAir (paket Community, gratis) | Pembanding real-time di website | Ya |
| Kaggle (API token) | Unduh dataset | Ya |
| OpenAQ (API key) | Uji Indonesia | Opsional |
| Mapillary (access token) | Uji Indonesia | Opsional |

Setelah Fase 1 selesai:

```bash
cp .env.example .env
sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 24)|" .env   # password acak
nano .env
```

`POSTGRES_PASSWORD` wajib diganti dan hanya boleh huruf dan angka. Perintah `sed` di atas membuatkannya.
Isi kuncinya di `.env` saja. Jangan tempel kunci ke chat Claude, dan jangan commit `.env`.

### A10. Kerjakan fase di laptop

Urutan: **Fase 0 → 1 → 2 → 3 → 4 → 4b → 5 → 6** dari `PROMPTS.md`. Di laptop, gunakan `PROFILE=laptop`
(data kecil, epoch sedikit) untuk memastikan seluruh alur berjalan. Angka akhir diambil di lab.

---

## B. Kerja sehari-hari di laptop

```bash
wsl -d AirLens          # dari PowerShell, atau buka lewat VS Code
cd ~/AirLens
git pull

make up                 # nyalakan layanan (setelah Fase 1)
make logs               # lihat log
make test               # jalankan test
make down               # matikan layanan
```

Buka http://localhost:8080 di browser Windows untuk website, http://localhost:5000 untuk MLflow.
Website memakai model `production` dari MLflow; bila belum ada model terlatih, jalankan dulu `make train SMOKE=1`
(model uji, ditandai "Model uji" di website). API memuat ulang model otomatis saat alias `production` berpindah.

Saat memulai sesi Claude Code baru, kirim prompt **"melanjutkan sesi baru"** dari `PROMPTS.md`.

Setiap akhir hari:

```bash
git add -A && git commit -m "<apa yang dikerjakan>" && git push
```

---

## C. Menjalankan di lab komputer kampus

Di lab cukup **terminal Ubuntu** (tanpa VS Code/Claude Code). Perintah lengkap yang tinggal disalin satu blok demi
satu blok ada di **`AirLens_perintah_lab.txt`**: buka Ubuntu → clone → `.env` → `make lab-all PROFILE=lab` → bawa
pulang arsip → push hasil ringkas → bersihkan. Bagian ini menjelaskan apa yang terjadi di balik perintah tersebut.

### C1. Sebelum berangkat (di laptop)

- [ ] Semua perubahan sudah di-commit dan di-push (lab memakai `git clone` dari GitHub).
- [ ] Kunci di password manager: `IQAIR_API_KEY`, `KAGGLE_USERNAME`, `KAGGLE_KEY`, dan **token GitHub** (scope `repo`).
      Push tetap butuh token walaupun repo publik.
- [ ] Cadangan zip India–Nepal di Google Drive, untuk berjaga-jaga bila Kaggle bermasalah (sha256 di `DATA_CARD.md`).
- [ ] Tempat menyimpan arsip hasil (Google Drive atau flash disk).

### C2. Satu perintah: `make lab-all PROFILE=lab`

Tahapan (`scripts/lab_all.sh`):

| Tahap | Isi |
|---|---|
| setup-check | alat (`make`, `git`, `curl`, `openssl`), Docker, disk ≥ 40 GB, RAM, `.env`, GPU di container (CUDA 12.6), LM Studio |
| layanan | menyalakan `db` dan `mlflow` |
| migrasi | membuat/memperbarui skema database (`make migrate`) |
| data | unduh (checksum, bisa dilanjutkan) → bersihkan → dedup → split → manifest |
| train | baseline + CNN di GPU, kalibrasi dan ambang di validasi, daftarkan `production` |
| eval | evaluasi test lewat ONNX (+ Qwen2.5-VL pada 300 foto bila `VLM_BASE_URL` terjangkau) |
| export | arsip `results/airlens_results_lab_<waktu>.tar.gz` |

Durasi, status, dan pemakaian disk tiap tahap tercatat di `logs/lab_<waktu>_lab/timings.tsv` dan `RINGKASAN.txt`.
Bila satu tahap gagal, tahap berikutnya dilewati, tetapi **export tetap dijalankan** agar hasil parsial tidak hilang.

Jalur darurat (tercatat, tidak tersembunyi):
- `AIRLENS_DATA_SOURCES=pm25vision,india_nepal make lab-all PROFILE=lab`: tanpa Dhaka, bila unduhan Zenodo terlalu
  lambat. File perintah lab mengukur kecepatannya dulu.
- `SKIP_CHECK=1 make lab-all PROFILE=lab`: tetap jalan walau setup-check gagal (mis. GPU tidak terdeteksi; CPU sangat lambat).
- `make lab-all PROFILE=lab SMOKE=1`: hanya membuktikan alur (1 epoch).

### C3. Perkiraan waktu dan disk (diukur)

Diukur dengan **simulasi klon bersih** di laptop: salinan bersih repo, volume baru,
`make lab-all PROFILE=laptop SMOKE=1` (subset 10% lokasi, CPU 4 inti). Dua kali dijalankan pada 2026-11-13:

| Tahap | Laptop, run 1 | Laptop, run 2 | Catatan untuk lab |
|---|---:|---:|---|
| setup-check | 45 dtk | 10 dtk | + uji GPU (unduh image CUDA 12.6 ~90 MB) |
| layanan | 43 dtk | 31 dtk | |
| migrasi | — | 15 dtk | (belum ada di run 1; run 1 gagal karena itu) |
| data | 5 mnt 50 dtk | **30 mnt 25 dtk** | Unduhan PM25Vision ~1 GB sangat bergantung jaringan (0,5–4 MB/s). Lab menambah **Dhaka 4,5 GB** (Zenodo, dari laptop ~0,15 MB/s) dan memproses data penuh, sekitar 10× gambar laptop |
| train (SMOKE) | 10 mnt 29 dtk* | 4 mnt 17 dtk | Lab: pelatihan penuh 2 CNN, maks 33 epoch di GPU. **Belum diukur**; ukur dulu dengan SMOKE |
| eval | — | 26 dtk | Lab: test ~3.000 foto + VLM 300 foto |
| export | 45 dtk | 10 dtk | |
| **total** | gagal di train | **36 mnt 21 dtk** | |

\* Run 1 gagal di train (skema database belum ada → ditambahkan tahap migrasi).

Disk (laptop): data subset 1,7 GB; image Docker proyek ~10 GB (trainer CPU 2,7 GB, mlflow 1,3 GB, api 0,8 GB, ...);
arsip hasil 49 MB. Di lab, image trainer **CUDA** (unduhan ~3 GB terkompresi) jauh lebih besar setelah terpasang, dan
arsip Dhaka diekstrak (~4,5 GB tambahan). Karena itu setup-check mensyaratkan disk kosong ≥ 40 GB. Angka lab yang
sebenarnya akan tercatat di `timings.tsv` setelah sesi lab pertama.

### C4. Isi arsip hasil (`make export-results PROFILE=lab`)

`results/`, bundle model (ONNX + metadata), `logs/`, ringkasan data (report, manifest, data_version), **volume
artefak MLflow**, **dump database `mlflow` dan `airlens`**, `ENVIRONMENT.txt` (tanpa rahasia), dan
`MANIFEST.sha256`. Arsip diperiksa agar tidak memuat nilai rahasia dari `.env`. Arsip dibawa lewat Google Drive/flash
disk (tidak masuk git); yang di-push dari lab hanya ringkasan kecil: tabel evaluasi, grafik, `timings.tsv`,
`RINGKASAN.txt`, dan `data_report_lab.json`.

### C5. Kembali ke laptop

Ekstrak arsip hasil (`tar -xzf airlens_results_lab_*.tar.gz`), lalu kerjakan **Fase 7** (laporan). Memulihkan
riwayat MLflow lab ke laptop butuh volume `mlflow` yang kosong (dump lab akan bentrok dengan riwayat laptop); langkahnya
dibahas di Fase 7 bila diperlukan.

---

## D. Pemecahan masalah

| Gejala | Kemungkinan penyebab dan solusi |
|---|---|
| `permission denied` saat menjalankan docker | Pengguna belum di grup docker atau sesi belum diperbarui. Jalankan `wsl --shutdown` di PowerShell, buka lagi distro. |
| `docker: command not found` di AirLens | Integrasi Docker Desktop untuk AirLens belum aktif, atau Docker Engine belum dipasang. Ulangi Fase S. |
| Website tidak terbuka di localhost:8080 | Cek `docker compose ps` dan `make logs`. Pastikan tidak ada aplikasi lain memakai port 8080. |
| LM Studio tidak terjangkau dari container | Server LM Studio belum dinyalakan, belum melayani jaringan lokal, atau firewall memblokir port 1234. Ulangi pemeriksaan Fase 0. |
| GPU tidak terlihat di container | Driver NVIDIA di Windows atau NVIDIA Container Toolkit di WSL belum siap. Jalankan Fase 0 untuk diagnosis. |
| `make data` berhenti saat mengunduh | Koneksi terputus. Jalankan ulang; unduhan dilanjutkan dari posisi terakhir dan checksum diverifikasi. |
| Disk penuh | `docker system df` untuk melihat pemakaian, `docker system prune` untuk membersihkan image dan container yang tidak dipakai. |
| `code` tidak dikenali di WSL | Buka VS Code di Windows → WSL: Connect to WSL using Distro → AirLens. |
| Error aneh di skrip `.sh` (`\r`) | Line ending CRLF. Pastikan `.gitattributes` ada, lalu `git add --renormalize .`. |
| Proyek terasa sangat lambat | Proyek berada di `/mnt/c/...`. Pindahkan ke `~/AirLens`. |
| `claude` tidak ditemukan | Buka terminal baru atau `source ~/.bashrc`, lalu `claude doctor`. |
| `wsl --shutdown` di terminal Linux hanya mencetak bantuan "Wsman" | Di Ubuntu, `wsl` adalah program lain. Pakai `wsl.exe --shutdown` dari Linux, atau `wsl --shutdown` di PowerShell. |
| `make up` gagal: `isi POSTGRES_PASSWORD di .env` | `.env` belum dibuat atau password kosong. Lihat A9, lalu `make setup-check`. |
| Website: "Model belum tersedia" | Belum ada model `production` di MLflow. Jalankan `make train SMOKE=1` (laptop) atau `make train PROFILE=lab`. Cek `curl localhost:8000/model`. |
| Layanan `unhealthy` setelah `make up` | `make ps` untuk melihat yang bermasalah, `docker compose logs <layanan>` untuk penyebabnya. |
| Password Postgres diganti tetapi db menolak login | Password hanya dipakai saat volume database pertama kali dibuat. Kembalikan password lama, atau (menghapus semua isi db) `docker compose down -v`. |

---

## Struktur proyek (setelah Fase 1)

```
AirLens/
├── CLAUDE.md            aturan proyek untuk Claude Code
├── PROMPTS.md           prompt per fase
├── README.md            dokumen ini
├── ARCHITECTURE.md      diagram arsitektur dan pipeline (Mermaid)
├── DECISIONS.md         keputusan penting dan alasannya
├── DATA_CARD.md         sumber, lisensi, dan statistik data (Fase 2)
├── ENVIRONMENT.md       hasil cek lingkungan laptop dan lab (Fase 0)
├── SETUP_LOG.md         catatan penyiapan distro (Fase S)
├── compose.yaml         layanan utama
├── compose.gpu.yaml     tambahan GPU untuk lab
├── Dockerfile           image Python (target api, scheduler, trainer, dev)
├── Makefile             perintah umum
├── .env.example         contoh variabel lingkungan
├── requirements/        *.in (daftar) dan *.txt (terkunci dengan hash, dari `make lock`)
├── config/              laptop.yaml, lab.yaml
├── api/                 FastAPI
├── web/                 frontend (nginx)
├── mlflow/              image server MLflow
├── db/init/             pembuatan database mlflow dan airlens_test
├── trainer/             pelatihan dan evaluasi
├── scheduler/           monitoring berkala
├── scripts/             setup_check.sh
├── src/airlens/         kode bersama (config, skema db, migrasi Alembic)
├── tests/               pytest
├── data/                (tidak di-commit)
├── artifacts/           (tidak di-commit)
└── results/             hasil evaluasi dan laporan monitoring
```

## Perintah make

| Perintah | Fungsi | Tersedia setelah |
|---|---|---|
| `make setup-check` | Cek lokasi proyek, Docker, `.env`, GPU (lab), LM Studio | Fase 1 |
| `make up` / `down` / `logs` / `ps` | Nyalakan (menunggu semua sehat), matikan, lihat log, lihat status | Fase 1 |
| `make test` | Jalankan pytest di container (database `airlens_test`) | Fase 1 |
| `make ui-test` | Uji UI di Chrome headless: alur, galat, 360 px, keyboard, reduced motion, kontras. Hasil di `results/ui/` | Fase 4 |
| `make docs-check` | Validasi diagram Mermaid di `ARCHITECTURE.md` (render di Chrome headless) | Fase 5 |
| `make lock` | Kunci ulang dependency Python setelah mengubah `requirements/*.in` | Fase 1 |
| `make data PROFILE=...` | Unduh, bersihkan, dedup, split, manifest (laptop: subset 10% lokasi; lab: penuh + Dhaka 4,5 GB). Lihat `DATA_CARD.md` | Fase 2 |
| `make train PROFILE=...` | Latih baseline dan CNN, kalibrasi + ambang di validasi, daftarkan model `production` di MLflow. `SMOKE=1` = uji asap singkat | Fase 3 |
| `make eval PROFILE=...` | Evaluasi di test lewat ONNX, buat `results/eval_<tanggal>.csv` dan grafik | Fase 3 |
| `make monitor [SINCE=… UNTIL=…]` | Jalankan job monitoring mingguan sekarang (drift, keyakinan, IQAir, shadow); laporan di `results/monitoring/` | Fase 5 |
| `make retrain` | Latih ulang, daftarkan sebagai `challenger` (API menjalankannya dalam shadow mode) | Fase 5 |
| `make promote` | Bandingkan challenger vs production (test tetap + shadow); promosi hanya bila kriteria config terpenuhi | Fase 5 |
| `make rollback [VERSION=n]` | Kembalikan alias production ke versi sebelumnya tanpa build ulang | Fase 5 |
| `make drift-sim` | Simulasi drift lewat API: membuktikan peringatan menyala (data bergeser) dan tidak (data normal) | Fase 5 |
| `make lab-all PROFILE=lab` | Seluruh alur di lab: cek → migrasi → data → latih → evaluasi → kemas; durasi tiap tahap di `logs/` | Fase 6 |
| `make export-results PROFILE=…` | Arsip bertanggal: results, model, log, volume MLflow, dump database mlflow + airlens | Fase 6 |
| `make migrate` | Buat/perbarui skema database (otomatis sebelum train/retrain/promote/rollback) | Fase 6 |
