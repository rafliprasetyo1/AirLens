#!/usr/bin/env bash
# Cek cepat lingkungan sebelum `make up`. Tidak mengubah sistem.
# Pemakaian: scripts/setup_check.sh laptop|lab
set -u
PROFILE="${1:-laptop}"
# Harus sama dengan versi CUDA trainer (compose.gpu.yaml: cu126). Image 12.8 mensyaratkan driver lebih baru dan
# bisa membuat cek ini GAGAL padahal pelatihan CUDA 12.6 berjalan.
CUDA_IMAGE="nvidia/cuda:12.6.3-base-ubuntu24.04"
MIN_RAM_GB=6
CURL_IMAGE="curlimages/curl:8.11.1"
fail=0

ok()   { printf '  OK        %s\n' "$*"; }
bad()  { printf '  GAGAL     %s\n' "$*"; fail=1; }
skip() { printf '  DILEWATI  %s\n' "$*"; }

echo "AirLens setup-check (profil: $PROFILE)"

case "$(pwd -P)" in
  /mnt/*) bad "proyek ada di $(pwd -P); pindahkan ke ~/AirLens" ;;
  *)      ok "lokasi proyek $(pwd -P)" ;;
esac

for tool in make git curl openssl; do
  command -v "$tool" >/dev/null 2>&1 && ok "$tool tersedia" || bad "$tool belum terpasang (sudo apt-get install -y $tool)"
done

case "$PROFILE" in
  lab) need=40 ;;  # unduhan lab ~10 GB, tetapi image CUDA terpasang dan arsip Dhaka yang diekstrak jauh lebih besar
  *)   need=15 ;;
esac
free_gb=$(df -BG --output=avail . | tail -1 | tr -dc '0-9')
if [ "${free_gb:-0}" -ge "$need" ]; then ok "disk kosong ${free_gb} GB (butuh >= ${need} GB)"; else bad "disk kosong ${free_gb} GB < ${need} GB yang dibutuhkan profil $PROFILE"; fi
ram_gb=$(awk '/MemTotal/ {printf "%.1f", $2/1048576}' /proc/meminfo)
if awk -v r="$ram_gb" -v m="$MIN_RAM_GB" 'BEGIN { exit !(r >= m) }'; then ok "RAM WSL ${ram_gb} GB"
else skip "RAM WSL ${ram_gb} GB < ${MIN_RAM_GB} GB: pelatihan bisa kehabisan memori (kurangi num_workers di config)"; fi

if docker info >/dev/null 2>&1; then
  ok "docker $(docker version --format '{{.Server.Version}}') ($(docker info --format '{{.OperatingSystem}}'))"
else
  bad "docker tidak bisa dipakai tanpa sudo (lihat README bagian D)"
fi

if v=$(docker compose version --short 2>/dev/null); then ok "docker compose $v"; else bad "docker compose tidak ada"; fi

env_get() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2-; }
if [ ! -f .env ]; then
  bad ".env belum ada (cp .env.example .env)"
else
  pw="$(env_get POSTGRES_PASSWORD)"
  if [ -z "$pw" ] || [ "$pw" = "ganti-dengan-password-acak" ]; then
    bad "POSTGRES_PASSWORD di .env belum diganti"
  elif ! printf '%s' "$pw" | grep -qE '^[A-Za-z0-9]+$'; then
    bad "POSTGRES_PASSWORD hanya boleh huruf dan angka"
  else
    ok ".env ada, POSTGRES_PASSWORD terisi"
  fi
  [ -n "$(env_get IQAIR_API_KEY)" ] && ok "IQAIR_API_KEY terisi" || skip "IQAIR_API_KEY kosong (dibutuhkan mulai Fase 4)"
fi

if [ "$PROFILE" = "lab" ]; then
  if timeout 120 docker run --rm --gpus all "$CUDA_IMAGE" nvidia-smi -L >/tmp/airlens-gpu.txt 2>&1; then
    ok "GPU di container: $(head -1 /tmp/airlens-gpu.txt)"
  else
    bad "GPU tidak terlihat di container: $(tail -1 /tmp/airlens-gpu.txt)"
  fi
else
  skip "GPU (profil laptop memakai CPU)"
fi

vlm="$(env_get VLM_BASE_URL)"
if [ -z "$vlm" ]; then
  skip "LM Studio (VLM_BASE_URL kosong; opsional)"
elif docker run --rm "$CURL_IMAGE" -sf -m 5 "$vlm/models" >/dev/null 2>&1; then
  ok "LM Studio terjangkau dari container: $vlm"
else
  skip "LM Studio tidak terjangkau di $vlm (opsional; nyalakan server LM Studio bila perlu)"
fi

exit $fail
