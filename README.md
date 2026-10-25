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

Lab sudah punya WSL Ubuntu 24.04, Docker, dan LM Studio. Kamu tidak perlu membuat distro AirLens di lab; cukup
folder `~/AirLens` di distro Ubuntu yang ada.

### C1. Sebelum berangkat (di laptop)

- [ ] Fase 0–6 selesai dan `make lab-all PROFILE=laptop` berhasil dari klon bersih.
- [ ] Semua perubahan sudah di-push ke GitHub.
- [ ] Nilai `.env` tersimpan aman (password manager), bukan di flash disk tanpa enkripsi.
- [ ] Personal Access Token GitHub siap, sebaiknya token sementara yang kedaluwarsa dalam beberapa hari.
- [ ] Siapkan tempat menyimpan hasil (Google Drive atau flash disk).

### C2. Buka Ubuntu dan cek Docker

PowerShell di komputer lab:

```powershell
wsl -l -v
wsl -d Ubuntu-24.04
```

(Pakai nama distro yang muncul di daftar.) Lalu:

```bash
docker compose version
docker run --rm hello-world
```

### C3. Ambil proyek

```bash
cd ~
git clone https://github.com/<username-github>/AirLens.git
cd AirLens
cp .env.example .env
nano .env               # isi kunci API, set APP_PROFILE=lab
```

### C4. Siapkan LM Studio (opsional, untuk pembanding Qwen-VL)

1. Buka LM Studio di Windows, unduh **Qwen2.5-VL** dengan ukuran terbesar yang ditandai muat di GPU lab.
2. Muat modelnya, buka tab **Developer**, nyalakan server, dan aktifkan opsi melayani di jaringan lokal.
3. Kalau diminta, izinkan LM Studio di Windows Firewall untuk jaringan privat (port 1234).
4. Catat nama model persisnya:

```bash
curl http://<alamat-windows>:1234/v1/models
```

Alamat Windows ditentukan oleh Fase 0 (lihat `ENVIRONMENT.md`). Isi `VLM_BASE_URL` dan `VLM_MODEL` di `.env`.

### C5. Cek lingkungan lab

```bash
make setup-check PROFILE=lab
```

Atau, kalau Claude Code dipasang di lab, kirim prompt **Fase 0**. Pastikan GPU terlihat di container. Kalau tidak,
pelatihan tetap berjalan di CPU tetapi jauh lebih lama; laporkan di catatan.

### C5b. Data India–Nepal di lab

Isi `KAGGLE_USERNAME` dan `KAGGLE_KEY` di `.env`, **atau** salin zip yang sama dari laptop ke
`data/raw/india_nepal/air-pollution-image-dataset-from-india-and-nepal.zip`. Cocokkan sha256-nya dengan `DATA_CARD.md`:

```bash
sha256sum data/raw/india_nepal/*.zip
```

### C6. Jalankan semuanya

```bash
make lab-all PROFILE=lab
```

Ini mengunduh data, melatih, mengevaluasi semua model (termasuk Qwen-VL bila terjangkau), dan mengemas hasil.
Perkiraan waktu dan ruang disk ada di bagian akhir README setelah Fase 6.

Untuk melihat progres: `make logs` di terminal lain, atau MLflow di http://localhost:5000.

### C7. Bawa pulang hasil

```bash
make export-results
cp results/airlens_results_*.tar.gz /mnt/c/Users/<user-lab>/Desktop/
```

Lalu unggah arsip itu ke Google Drive atau salin ke flash disk. **Lakukan sebelum logout**, karena data di
komputer lab bisa terhapus.

### C8. Bersihkan sebelum pergi

```bash
make down
rm .env
rm -f ~/.git-credentials
git config --global --unset credential.helper
```

Kalau memakai Claude Code di lab, jalankan `/logout` di dalam Claude Code. Matikan server LM Studio.
Hapus atau cabut Personal Access Token di GitHub setelah selesai. Opsional: hapus folder `~/AirLens` dan
jalankan `docker system prune` bila ruang disk lab perlu dibebaskan.

### C9. Kembali ke laptop

Ekstrak arsip hasil ke `~/AirLens/results/` di laptop, lalu kerjakan **Fase 7** (laporan).

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
| `make lab-all PROFILE=lab` | Seluruh alur di lab | Fase 6 |
| `make export-results` | Kemas hasil untuk dibawa pulang | Fase 6 |
