# ENVIRONMENT — hasil Fase 0

Status: **OK** / **GAGAL** / **DILEWATI** (tidak relevan atau tidak tersedia di mesin ini, bukan kegagalan).

## Laptop (diperiksa 2026-10-24)

| Pemeriksaan | Hasil | Status |
|---|---|---|
| Nama distro | `AirLens` (`$WSL_DISTRO_NAME`) | OK |
| Ubuntu | 24.04.5 LTS, kernel 6.18.54.1-microsoft-standard-WSL2 | OK |
| WSL | 3.0.3.0, Windows 10.0.26300, mode jaringan `nat` | OK |
| Lokasi proyek | `/home/rafli_1/AirLens` (ext4 WSL, bukan `/mnt/c`) | OK |
| Docker | **Docker Desktop 4.92.0** (integrasi WSL), Engine 29.8.0, CLI dari `/mnt/wsl/docker-desktop/cli-tools` | OK |
| Docker Compose | v5.5.1 | OK |
| Disk | 953 GB bebas dari 1007 GB | OK |
| RAM | Fisik 7,4 GB; WSL 3,8 GiB (`.wslconfig`: `memory=4GB`, `processors=4`, `swap=4GB`); Docker melihat 3,8 GiB, 4 CPU | OK, sempit |
| GPU di container | Laptop hanya punya **AMD Radeon (iGPU)**, tanpa NVIDIA | DILEWATI |
| LM Studio dari container | `http://host.docker.internal:1234/v1` berhasil | OK |

### Bukti

```
$ docker version  ->  client 29.8.0 | server 29.8.0 | Docker Desktop 4.92.0 (240144)
$ docker compose version  ->  Docker Compose version v5.5.1
$ powershell Get-CimInstance Win32_VideoController
AMD Radeon(TM) Graphics | driver 31.0.12044.37003
$ docker run --rm --gpus all nvidia/cuda:12.8.1-base-ubuntu24.04 nvidia-smi
docker: Error response from daemon: ... error running prestart hook #0: exit status 1, ...
nvidia-container-cli: initialization error: WSL environment detected but no adapters were found
(exit=125)
```

Penyebab GPU tidak terlihat: tidak ada GPU NVIDIA, jadi tidak ada adapter CUDA untuk WSL. Ini sesuai harapan
karena pelatihan berat dijalankan di lab. Catatan: percobaan pertama tanpa `timeout` sempat menggantung lebih
dari 5 menit sebelum dihentikan. Selalu pakai `timeout` untuk uji ini.

Uji LM Studio dari container sementara (`curlimages/curl:8.11.1`):

```
host.docker.internal -> 192.168.65.254
## http://host.docker.internal:1234/v1/models
{ "data": [ { "id": "qwen2.5-1.5b-instruct", ... }, { "id": "text-embedding-nomic-embed-text-v1.5", ... } ] }
## http://<gateway WSL 172.25.96.1>:1234/v1/models
curl: (7) Failed to connect to gw port 1234 after 2025 ms: Could not connect to server
```

- Dengan **Docker Desktop**, `host.docker.internal` menunjuk ke Windows, sehingga ini alamat yang berhasil.
  IP gateway WSL tidak berhasil.
- Model yang termuat (`qwen2.5-1.5b-instruct`) **hanya teks** dan tidak bisa membaca gambar. Pembanding zero-shot
  butuh model **Qwen2.5-VL**, yang direncanakan di lab (RAM laptop tidak cukup untuk VLM sambil menjalankan compose).

### Nilai `.env` laptop

```
APP_PROFILE=laptop
VLM_BASE_URL=http://host.docker.internal:1234/v1
```

## Lab (belum diperiksa)

Jalankan Fase 0 lagi di mesin lab. Hal yang perlu dipastikan di sana:

| Pemeriksaan | Status |
|---|---|
| Distro, Ubuntu, lokasi proyek | BELUM |
| Docker Desktop atau Docker Engine | BELUM. Ini menentukan alamat LM Studio: Desktop memakai `host.docker.internal`; Engine memakai IP gateway WSL atau mode `mirrored` |
| `docker run --rm --gpus all nvidia/cuda:12.8.1-base-ubuntu24.04 nvidia-smi` | BELUM |
| LM Studio + model Qwen2.5-VL dari container | BELUM |
| RAM, disk | BELUM |

### Nilai `.env` lab

```
APP_PROFILE=lab
VLM_BASE_URL=<diisi setelah uji di lab>
```
