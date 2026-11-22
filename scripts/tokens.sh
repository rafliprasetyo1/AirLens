#!/usr/bin/env bash
# `make tokens`: isi SENSOR_TOKEN dan NODE_TOKEN acak di .env bila masih kosong (wajib di mode expo). Nilai tidak dicetak;
# untuk mengisi formulir di tools/flash.html, baca dari .env di komputer ini: grep SENSOR_TOKEN .env
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { echo ".env belum ada: cp .env.example .env"; exit 1; }
for k in SENSOR_TOKEN NODE_TOKEN; do
  if grep -qE "^$k=.+" .env; then echo "$k sudah terisi (tidak diubah)"; continue; fi
  v="$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
  if grep -qE "^$k=" .env; then sed -i "s/^$k=.*/$k=$v/" .env; else echo "$k=$v" >> .env; fi
  echo "$k diisi (acak, 32 karakter)"
done
