#!/usr/bin/env bash
# `make tokens`: isi SENSOR_TOKEN dan NODE_TOKEN acak di .env bila masih kosong (wajib di mode expo). Nilai tidak dicetak;
# `make tokens ROTATE=1`: ganti keduanya dengan nilai acak baru (mis. setelah token sempat lewat jalur tanpa enkripsi);
# lalu nyalakan ulang api (docker compose up -d api) dan simpan token baru ke ESP32 lewat tools/flash.html.
# untuk mengisi formulir di tools/flash.html, baca dari .env di komputer ini: grep SENSOR_TOKEN .env
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { echo ".env belum ada: cp .env.example .env"; exit 1; }
for k in SENSOR_TOKEN NODE_TOKEN; do
  if [ -z "${ROTATE:-}" ] && grep -qE "^$k=.+" .env; then echo "$k sudah terisi (tidak diubah)"; continue; fi
  v="$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
  if grep -qE "^$k=" .env; then sed -i "s/^$k=.*/$k=$v/" .env; else echo "$k=$v" >> .env; fi
  echo "$k diisi (acak, 32 karakter)${ROTATE:+, menggantikan nilai lama}"
done
