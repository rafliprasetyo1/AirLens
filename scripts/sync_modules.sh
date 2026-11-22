#!/usr/bin/env bash
# Salin modul perakitan dari docs/modules/ (sumber) ke web/static/modules/ agar bisa dibuka dari menu Build guides.
# Satu-satunya perubahan: tautan Google Fonts dihapus, sehingga website tidak meminta apa pun ke domain luar dan
# tetap rapi saat booth offline (modul memakai font cadangan yang sudah ada di CSS-nya). Folder arsip/ tidak disalin.
# Jalankan ulang setiap kali modul di docs/modules/ berubah:  bash scripts/sync_modules.sh
set -euo pipefail
cd "$(dirname "$0")/.."
src=docs/modules
dst=web/static/modules
mkdir -p "$dst"
for f in "$src"/merakit-node-*.html; do
  out="$dst/$(basename "$f")"
  sed -E '/<link[^>]+fonts\.(googleapis|gstatic)\.com[^>]*>/d' "$f" > "$out"
  if grep -qE 'fonts\.(googleapis|gstatic)\.com' "$out"; then
    echo "GAGAL: $out masih memuat tautan Google Fonts" >&2
    exit 1
  fi
  echo "disalin: $f -> $out"
done
