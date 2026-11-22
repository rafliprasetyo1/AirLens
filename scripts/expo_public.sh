#!/usr/bin/env bash
# `make expo-public` (prompt 7): buka AirLens ke internet lewat ngrok (akun free: domain acak per sesi).
# - ngrok dijalankan di latar (log: logs/ngrok.log). Bila sudah berjalan, sesi yang ada dipakai ulang.
# - Domain sesi dibaca dari API lokal ngrok (127.0.0.1:4040) lalu DISIMPAN/DITIMPA ke NGROK_DOMAIN di .env.
#   Restart ngrok = domain baru = .env ditimpa lagi. URL ESP32 diperbarui lewat tools/flash.html (Set WiFi), tanpa flash ulang.
# - `scripts/expo_public.sh stop` (make expo-public-stop) mematikan ngrok; layanan Docker tetap jalan (make down).
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
PIDFILE=logs/ngrok.pid
mkdir -p logs

if [ "${1:-}" = stop ]; then
  if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then kill "$(cat "$PIDFILE")"; echo "ngrok dimatikan."; else echo "ngrok tidak berjalan."; fi
  rm -f "$PIDFILE"; exit 0
fi

command -v ngrok >/dev/null || { echo "ngrok belum terpasang di WSL. Pasang (tanpa sudo):"
  echo "  mkdir -p ~/.local/bin && curl -sSL https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz | tar -xz -C ~/.local/bin ngrok"; exit 1; }
cfg="$(ngrok config check 2>&1 | grep -oE '/[^ ]+\.yml' | head -1 || true)"
if [ -z "$cfg" ] || ! grep -qE '^\s*authtoken:\s*\S+' "$cfg"; then
  echo "Authtoken ngrok belum dipasang. Jalankan sendiri (token dari dashboard.ngrok.com, jangan ditempel di chat):"
  echo "  ngrok config add-authtoken <TOKEN>"; exit 1
fi

tunnel_url() { { curl -s 127.0.0.1:4040/api/tunnels 2>/dev/null || true; } | python3 -c "import sys,json
try: t=json.load(sys.stdin).get('tunnels',[])
except Exception: t=[]
print(next((x['public_url'] for x in t if x['public_url'].startswith('https') and x['config']['addr'].endswith(':8080')),''))" 2>/dev/null || true; }

url="$(tunnel_url)"
if [ -z "$url" ]; then
  nohup ngrok http 8080 --log=logs/ngrok.log > /dev/null 2>&1 &
  echo $! > "$PIDFILE"
  for _ in $(seq 1 30); do sleep 1; url="$(tunnel_url)"; [ -n "$url" ] && break; done
fi
[ -n "$url" ] || { echo "ngrok tidak memberi alamat publik; lihat logs/ngrok.log"; exit 1; }
domain="${url#https://}"
python3 - "$domain" <<'PY'
import re, sys
d = sys.argv[1]
if not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", d):
    sys.exit(f"alamat ngrok tidak wajar: {d!r}")
lines = open(".env").read().split("\n")
if any(l.startswith("NGROK_DOMAIN=") for l in lines):
    lines = [f"NGROK_DOMAIN={d}" if l.startswith("NGROK_DOMAIN=") else l for l in lines]
else:
    lines.append(f"NGROK_DOMAIN={d}")
open(".env", "w").write("\n".join(lines))
PY

cat <<EOF

AirLens publik (sesi ngrok ini; domain disimpan ke .env sebagai NGROK_DOMAIN):
  Website        : https://$domain/
  Halaman Beta   : https://$domain/beta.html
  URL sensor ESP32 (Set WiFi di flash.html):  https://$domain/api/sensor/readings
  Alat operator (HANYA dari komputer ini)  :  http://localhost:8080/tools/flash.html   http://localhost:8080/tools/recorder.html
Domain berganti bila ngrok di-restart: jalankan ulang perintah ini, lalu perbarui URL ESP32 dan QR.
Matikan ngrok: make expo-public-stop   (layanan Docker tetap jalan; matikan dengan make down)
EOF
