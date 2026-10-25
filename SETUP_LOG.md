# SETUP_LOG — Fase S (laptop, distro WSL `AirLens`)

Tanggal: 2026-10-24

## 1. Pemeriksaan awal

| Item | Hasil | Status |
|---|---|---|
| `$WSL_DISTRO_NAME` | `AirLens` | OK |
| Ubuntu | 24.04.5 LTS | OK |
| Kernel | 6.18.54.1-microsoft-standard-WSL2 | OK |
| systemd | PID 1 = systemd; `/etc/wsl.conf` sudah `systemd=true` | OK |
| `systemctl is-system-running` | `degraded` — hanya `getty@tty1` gagal (normal di WSL, tanpa TTY fisik) | OK (diabaikan) |
| Disk `/` | 953 GB bebas dari 1007 GB | OK |
| RAM WSL | 3,8 GiB total, swap 4 GiB, 4 CPU | PERHATIAN: README menyarankan `memory=6GB` di `.wslconfig` |
| Lokasi proyek | `/home/rafli_1/AirLens` (filesystem WSL, bukan `/mnt/c`) | OK |
| docker (awal) | `command not found` | — |

## 2. Docker

Pilihan: **Docker Desktop dengan integrasi WSL** (sudah terpasang di Windows; integrasi untuk `AirLens` diaktifkan
pengguna). Docker Engine **tidak** dipasang di distro (keduanya tidak boleh aktif bersamaan).

Bukti:

```
$ readlink -f /usr/bin/docker
/mnt/wsl/docker-desktop/cli-tools/usr/bin/docker
$ getent group docker
docker:x:1001:rafli_1
$ docker version  (lewat sg docker, sebelum sesi diperbarui)
client 29.8.0 | server 29.8.0 | Docker Desktop 4.92.0 (240144)
$ docker info
docker-desktop | Docker Desktop (containerized) | mem 4108935168 | cpus 4
$ docker compose version
Docker Compose version v5.5.1
$ docker run --rm hello-world
Hello from Docker!
```

Konsekuensi untuk Fase 0: dengan Docker Desktop, `host.docker.internal` dari container menunjuk ke **Windows**
(berbeda dengan asumsi Docker Engine di CLAUDE.md). Alamat LM Studio tetap harus diuji di Fase 0, bukan ditebak.

## 3. Perubahan yang dilakukan

| Perubahan | Oleh | Status |
|---|---|---|
| Integrasi WSL Docker Desktop untuk `AirLens` | pengguna (GUI Windows) | SELESAI |
| `rafli_1` masuk grup `docker` | Docker Desktop (otomatis) | SELESAI, berlaku setelah sesi baru |
| `/etc/wsl.conf` | — | tidak diubah (systemd sudah aktif) |
| `apt-get install make jq` (git, curl, ca-certificates sudah ada) | pengguna (butuh password sudo) | BELUM |
| `git config --global core.autocrlf=input`, `core.eol=lf`, `init.defaultBranch=main` | Claude | SELESAI |
| `git config --global user.name` / `user.email` | pengguna | SELESAI (`rafliprasetyo1`) |
| `.gitattributes` (`* text=auto eol=lf` + aturan biner) | Claude | SELESAI |
| `.gitignore` awal | Claude | SELESAI |
| `chmod 644` pada `CLAUDE.md`, `PROMPTS.md`, `README.md` (buang bit eksekusi) | Claude | SELESAI |
| `git init -b main` + config lokal `core.autocrlf=input`, `core.eol=lf` | Claude | SELESAI |

## 4. Uji penutup (setelah `wsl --shutdown`)

Percobaan 1 (2026-10-24, sebelum `wsl --shutdown` dan sebelum apt install):

```
$ id -nG
rafli_1 adm cdrom sudo dip plugdev users
$ docker run --rm hello-world
permission denied while trying to connect to the docker API at unix:///var/run/docker.sock
$ docker compose version
Docker Compose version v5.5.1
$ make --version / jq --version
TIDAK ADA / TIDAK ADA
```

| Uji | Status |
|---|---|
| `id -nG` memuat `docker` | GAGAL — sesi belum diperbarui (perlu `wsl --shutdown`) |
| `docker run --rm hello-world` tanpa sudo/sg | GAGAL — sebab sama; lewat `sg docker` sudah berhasil |
| `docker compose version` tanpa sudo | OK (v5.5.1) |
| `make --version`, `jq --version` | GAGAL — belum dipasang (butuh password sudo) |

Percobaan 2 (2026-10-24, setelah pengguna menjalankan `sudo apt-get install -y make jq` dan `wsl.exe --shutdown`;
boot WSL 20:17:55):

```
$ id -nG
rafli_1 adm cdrom sudo dip plugdev users docker
$ docker run --rm hello-world
Hello from Docker!            (exit=0, tanpa sudo/sg)
$ docker compose version
Docker Compose version v5.5.1
$ make --version | head -1 ; jq --version
GNU Make 4.3
jq-1.7
```

| Uji | Status |
|---|---|
| `id -nG` memuat `docker` | OK |
| `docker run --rm hello-world` tanpa sudo | OK |
| `docker compose version` tanpa sudo | OK (v5.5.1) |
| `make --version`, `jq --version` | OK (GNU Make 4.3, jq-1.7) |

## 5. Ringkasan perubahan sistem

- Paket apt baru: `make`, `jq` (git, curl, ca-certificates sudah ada sejak awal).
- Docker Desktop: integrasi WSL untuk distro `AirLens` diaktifkan; `rafli_1` ditambahkan ke grup `docker` (otomatis).
- `~/.gitconfig`: `user.name`, `user.email`, `core.autocrlf=input`, `core.eol=lf`, `init.defaultBranch=main`.
- Tidak diubah: `/etc/wsl.conf`, Docker Engine (tidak dipasang).

Catatan: di Ubuntu, perintah `wsl` adalah paket lain (*Wsman Shell Command Line*), bukan WSL Windows.
Dari dalam distro, pakai `wsl.exe --shutdown`, atau `wsl --shutdown` di PowerShell.

**Fase S: SELESAI.**
