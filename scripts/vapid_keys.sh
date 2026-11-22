#!/usr/bin/env bash
# `make vapid-keys`: buat pasangan kunci VAPID untuk Web Push dan tulis ke .env (tidak pernah dicetak, tidak di repo).
# Bila .env sudah berisi VAPID_PUBLIC_KEY, tidak ada yang diubah (kunci baru akan memutus semua subscription lama).
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { echo ".env belum ada: cp .env.example .env lalu isi" >&2; exit 1; }
if grep -qE '^VAPID_PUBLIC_KEY=.+' .env && grep -qE '^VAPID_PRIVATE_KEY=.+' .env; then
  echo "Kunci VAPID sudah ada di .env; tidak diubah."
  exit 0
fi
keys="$(docker compose -f compose.yaml run --rm --no-deps -T api python -m airlens_api.push generate | grep -E '^VAPID_(PUBLIC|PRIVATE)_KEY=.+')"
[ "$(printf '%s\n' "$keys" | wc -l)" -eq 2 ] || { echo "gagal membuat kunci VAPID" >&2; exit 1; }
tmp="$(mktemp)"
grep -vE '^VAPID_(PUBLIC_KEY|PRIVATE_KEY)=' .env > "$tmp" || true
printf '%s\n' "$keys" >> "$tmp"
grep -qE '^VAPID_SUBJECT=.+' "$tmp" || { grep -vE '^VAPID_SUBJECT=' "$tmp" > "$tmp.2" || true; mv "$tmp.2" "$tmp"; echo "VAPID_SUBJECT=mailto:airlens@example.com" >> "$tmp"; }
cat "$tmp" > .env
rm -f "$tmp"
echo "Kunci VAPID ditulis ke .env (VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT). Jalankan ulang: make up"
