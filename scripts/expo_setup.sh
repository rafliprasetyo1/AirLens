#!/usr/bin/env bash
# `make expo-setup` (prompt 7): satu perintah untuk komputer lab pada hari pameran (juga jalan di laptop).
#   doctor -> models-pull (model final dari dataset Kaggle privat) -> layanan pameran (db, mlflow, api, web) mode expo
#   -> ngrok (domain sesi disimpan ke .env) -> QR di terminal + docs/assets/qr_expo.png -> ringkasan alamat.
# Aman diulang (mis. setelah layanan mati atau ngrok restart).
set -uo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
step() { echo; echo "== $1"; }

step "1/5 doctor"
scripts/doctor.sh || { echo "Perbaiki masalah wajib di atas, lalu jalankan ulang: make expo-setup"; exit 1; }

step "2/5 mode expo (token wajib)"
grep -qE '^EXPO_MODE=' .env && sed -i 's/^EXPO_MODE=.*/EXPO_MODE=1/' .env || echo "EXPO_MODE=1" >> .env
echo "EXPO_MODE=1 di .env (sensor/node tanpa token ditolak). Matikan untuk pengembangan: EXPO_MODE=0"

step "3/5 model final (models-pull)"
if make --no-print-directory models-pull; then :; else
  echo "CATATAN: models-pull gagal/tersedia belum; layanan tetap dinyalakan dengan model yang sudah ada di MLflow mesin ini."
fi

step "4/5 layanan pameran"
docker compose -f compose.yaml up -d --build --wait db mlflow api web || { echo "Layanan gagal sehat: make logs"; exit 1; }

step "5/5 ngrok + QR"
scripts/expo_public.sh || exit 1
domain="$(grep -E '^NGROK_DOMAIN=' .env | cut -d= -f2)"
mkdir -p docs/assets
docker compose -f compose.yaml --profile train run --rm --build --no-deps -T -v "$PWD/docs/assets:/qr" trainer \
  python -m airlens_trainer.qr "https://$domain/" /qr/qr_expo.png 2>/dev/null | grep -vE "^(QR |#|time=)"
echo "QR tersimpan: docs/assets/qr_expo.png (cetak / tampilkan di layar booth). Domain berganti bila ngrok restart."
echo
echo "Selesai. Layar booth: http://localhost:8080 · pengunjung: https://$domain/ · cek ulang kapan saja: make doctor"
