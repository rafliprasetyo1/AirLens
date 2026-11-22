#!/usr/bin/env bash
# Gladi tanpa alat: ESP32 simulasi di Wokwi mengirim bacaan ke AirLens, kapan saja (laptop atau komputer lab).
#
#   make gladi        buka jalur HTTP sementara di ngrok (tunnel kedua, alamat HTTPS utama tidak berubah) dan cetak
#                     perintah SET untuk Serial Monitor Wokwi
#   make gladi-stop   tutup jalur itu, hapus data node gladi (wokwi-*), ganti SENSOR_TOKEN/NODE_TOKEN, nyalakan ulang api
#                     (KEEP_TOKENS=1: token tidak diganti, mis. bila ESP32 asli sudah menyimpan token yang sama)
#
# Kenapa HTTP: CPU ESP32 di Wokwi terlalu lambat untuk jabat tangan HTTPS, sehingga ngrok memutusnya (SSL EOF).
# Token ikut terkirim tanpa enkripsi lewat jalur ini, karena itu gladi-stop menggantinya. Alat asli selalu HTTPS.
# Token tidak pernah dicetak skrip ini; ambil dengan: grep ^SENSOR_TOKEN= .env
set -euo pipefail
cd "$(dirname "$0")/.."
API=http://localhost:4040/api/tunnels
NAME=gladi-http

agent_up() { curl -sf "$API" >/dev/null 2>&1; }

start() {
  agent_up || { echo "ngrok belum menyala. Jalankan dulu: make expo-public (atau make expo-setup)"; exit 1; }
  grep -qE "^SENSOR_TOKEN=.+" .env || { echo "SENSOR_TOKEN belum ada di .env. Jalankan dulu: make tokens"; exit 1; }
  url=$(curl -s "$API" | python3 -c "import json,sys; print(next((t['public_url'] for t in json.load(sys.stdin)['tunnels'] if t['name']=='$NAME'), ''))")
  if [ -z "$url" ]; then
    url=$(curl -s -X POST "$API" -H "Content-Type: application/json" \
      -d "{\"name\":\"$NAME\",\"proto\":\"http\",\"addr\":\"8080\",\"schemes\":[\"http\"]}" |
      python3 -c "import json,sys; print(json.load(sys.stdin).get('public_url',''))")
  fi
  [ -n "$url" ] || { echo "Gagal membuka jalur gladi di ngrok (lihat logs/ngrok.log)"; exit 1; }
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$url/api/health" || true)
  https_url=$(curl -s "$API" | python3 -c "import json,sys; print(next((t['public_url'] for t in json.load(sys.stdin)['tunnels'] if t['public_url'].startswith('https')), ''))")
  cat <<EOF
Jalur gladi terbuka (cek kesehatan: HTTP $code)
  Wokwi mengirim ke : $url/api/sensor/readings   (HTTP, khusus gladi)
  Pantau dari HP    : $https_url/beta.html        (pilih node wokwi-01)

1. Wokwi: tempel isi wokwi/beta/diagram.json, sketch.ino, airlens_roots.h (lihat wokwi/README.md), lalu Run.
2. Ambil token di terminal ini:  grep ^SENSOR_TOKEN= .env   (salin bagian setelah '=')
3. Tempel di kotak input Serial Monitor Wokwi, lalu Enter:
   SET {"ssid":"Wokwi-GUEST","pass":"","url":"$url/api/sensor/readings","token":"<SENSOR_TOKEN>","node":"wokwi-01"}
4. Tunggu {"event":"post","code":200}. Biarkan tab Wokwi tetap terlihat (tab latar belakang menjeda simulasi).
   Status Normal setelah ±4 menit; kombinasi uji ada di wokwi/README.md.

Selesai: make gladi-stop
EOF
}

stop() {
  if agent_up; then
    code=$(curl -s -o /dev/null -w '%{http_code}' -X DELETE "$API/$NAME")
    [ "$code" = 204 ] && echo "Jalur gladi ditutup." || echo "Jalur gladi tidak aktif (tidak ada yang ditutup)."
  else
    echo "ngrok tidak menyala; jalur gladi otomatis tertutup."
  fi
  # data node gladi tidak ikut tampil di pilihan node halaman Beta saat pameran
  docker compose -f compose.yaml exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -qAt -c "
    delete from sensor_readings where node_id like '"'"'wokwi-%'"'"' or node_id = '"'"'cek-token'"'"';
    delete from sensor_nodes where node_id like '"'"'wokwi-%'"'"' or node_id = '"'"'cek-token'"'"';"' \
    && echo "Data node gladi (wokwi-*) dihapus." || echo "Database tidak terjangkau; data node gladi tidak dihapus."
  if [ -n "${KEEP_TOKENS:-}" ]; then
    echo "Token TIDAK diganti (KEEP_TOKENS=1). Token sempat lewat jalur tanpa enkripsi; ganti sebelum pameran: make tokens ROTATE=1"
  else
    ROTATE=1 scripts/tokens.sh
    docker compose -f compose.yaml up -d api >/dev/null 2>&1 && echo "api dinyalakan ulang dengan token baru."
    echo "Bila ESP32 asli sudah menyimpan token lama: simpan token baru lewat http://localhost:8080/tools/flash.html (Set WiFi)."
  fi
}

case "${1:-start}" in
  start) start ;;
  stop) stop ;;
  *) echo "pakai: scripts/gladi.sh start|stop"; exit 2 ;;
esac
