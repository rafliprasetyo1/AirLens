#!/usr/bin/env bash
# `make doctor` (prompt 7): laporan kesiapan yang sama di laptop dan komputer lab. Nilai rahasia TIDAK pernah dicetak;
# hanya nama kunci .env dan status. Setiap masalah disertai perintah perbaikan. Kode keluar 1 bila ada masalah wajib.
set -uo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
PROBLEMS=0; WARN=0
ok()   { printf '  [OK]    %s\n' "$1"; }
bad()  { printf '  [MASALAH] %s\n           perbaiki: %s\n' "$1" "$2"; PROBLEMS=$((PROBLEMS+1)); }
warn() { printf '  [CATATAN] %s\n           saran: %s\n' "$1" "$2"; WARN=$((WARN+1)); }

echo "AirLens doctor · $(hostname) · $(date '+%Y-%m-%d %H:%M')"
echo "== Docker"
if docker version --format '{{.Server.Version}}' >/dev/null 2>&1; then
  ok "Docker $(docker version --format '{{.Server.Version}}'), Compose $(docker compose version --short 2>/dev/null)"
else bad "Docker tidak berjalan" "sudo service docker start   (atau buka ulang WSL)"; fi
imgs="$(docker images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null | grep -E '^airlens/' | sort | tr '\n' ' ')"
[ -n "$imgs" ] && ok "image: $imgs" || warn "image AirLens belum dibangun" "make up"
free_gb="$(df -BG --output=avail . | tail -1 | tr -dc '0-9')"
[ "${free_gb:-0}" -ge 15 ] && ok "ruang disk bebas ${free_gb} GB" || warn "ruang disk tinggal ${free_gb} GB" "hapus data lama: docker system prune (hati-hati)"

echo "== .env (hanya nama kunci, nilai tidak ditampilkan)"
if [ ! -f .env ]; then bad ".env tidak ada" "cp .env.example .env lalu isi"; else
  for k in POSTGRES_PASSWORD SENSOR_TOKEN NODE_TOKEN; do
    grep -qE "^$k=.+" .env && ok "$k terisi" || bad "$k kosong" "$([ "$k" = POSTGRES_PASSWORD ] && echo 'isi password acak di .env' || echo 'make tokens')"
  done
  for k in KAGGLE_USERNAME KAGGLE_KEY; do grep -qE "^$k=.+" .env && ok "$k terisi" || bad "$k kosong" "isi dari kaggle.com → Settings → API (untuk make models-pull)"; done
  grep -qE '^VAPID_PUBLIC_KEY=.+' .env && grep -qE '^VAPID_PRIVATE_KEY=.+' .env && ok "kunci VAPID (Web Push) terisi" \
    || warn "kunci VAPID kosong: notifikasi hanya saat tab terbuka" "make vapid-keys"
  grep -qE '^IQAIR_API_KEY=.+' .env && ok "IQAIR_API_KEY terisi" || warn "IQAIR_API_KEY kosong: pembanding IQAir tidak tampil" "isi dari iqair.com/dashboard/api"
  grep -qE '^NGROK_DOMAIN=.+' .env && ok "NGROK_DOMAIN terisi (sesi terakhir; ditimpa saat make expo-public)" || warn "NGROK_DOMAIN belum ada" "make expo-public (mengisi otomatis)"
fi

echo "== ngrok"
if command -v ngrok >/dev/null; then
  ok "$(ngrok version)"
  cfg="$(ngrok config check 2>&1 | grep -oE '/[^ ]+\.yml' | head -1 || true)"
  if [ -n "$cfg" ] && grep -qE '^\s*authtoken:\s*\S+' "$cfg"; then ok "authtoken ngrok terpasang"; else bad "authtoken ngrok belum dipasang" "ngrok config add-authtoken <TOKEN dari dashboard.ngrok.com>"; fi
else bad "ngrok belum terpasang" "mkdir -p ~/.local/bin && curl -sSL https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz | tar -xz -C ~/.local/bin ngrok"; fi

echo "== Kaggle CLI"
if docker compose -f compose.yaml --profile train run --rm --no-deps -T trainer kaggle datasets list --mine -p 1 >/tmp/doctor_kaggle.txt 2>&1; then
  ok "Kaggle CLI bisa login"
  grep -q 'airlens-models' /tmp/doctor_kaggle.txt && ok "dataset airlens-models ada" || warn "dataset airlens-models belum terlihat" "di laptop: make models-publish MODELS_APPROVED=1"
else bad "Kaggle CLI gagal login" "periksa KAGGLE_USERNAME / KAGGLE_KEY di .env"; fi
rm -f /tmp/doctor_kaggle.txt

echo "== Layanan dan model aktif"
if curl -sf localhost:8080/api/health >/tmp/doctor_h.json 2>/dev/null; then
  ok "website + API menyala (http://localhost:8080)"
  for ep in model beta/model; do
    curl -s "localhost:8080/api/$ep" | python3 -c "import sys,json
d=json.load(sys.stdin); m=d.get('model') or 'airlens-aqi'
print(f\"  [{'OK' if d.get('status')=='ok' else 'CATATAN'}]    {m}: {d.get('version') or '-'} ({d.get('status')})\")" 2>/dev/null
  done
else warn "layanan belum menyala" "make expo-setup (atau make up)"; fi
rm -f /tmp/doctor_h.json

echo "== Uji cepat"
if curl -sf localhost:8080/api/health >/dev/null 2>&1; then
  c="$(curl -s -o /dev/null -w '%{http_code}' -H 'Content-Type: application/json' -d '{"node_id":"doctor","mq2_rs_kohm":18}' localhost:8080/api/sensor/readings)"
  [ "$c" = 401 ] && ok "endpoint sensor menolak tanpa token (401)" || warn "endpoint sensor tanpa token menjawab $c" "make tokens lalu jalankan ulang layanan"
  c="$(curl -s -o /dev/null -w '%{http_code}' localhost:8080/beta.html)"; [ "$c" = 200 ] && ok "halaman Beta 200" || bad "halaman Beta $c" "make logs"
fi

echo
if [ "$PROBLEMS" -eq 0 ]; then echo "HASIL: siap ($WARN catatan)."; else echo "HASIL: $PROBLEMS masalah wajib, $WARN catatan. Perbaiki lalu jalankan ulang: make doctor"; fi
[ "$PROBLEMS" -eq 0 ]
