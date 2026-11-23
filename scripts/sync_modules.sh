#!/usr/bin/env bash
# Salin modul perakitan dari docs/modules/ (sumber) ke web/static/modules/ agar bisa dibuka dari menu Build guides.
# Perubahan saat menyalin:
#   1. tautan Google Fonts dihapus (website tidak meminta apa pun ke domain luar; font Archivo dari /vendor/fonts),
#   2. kepala navigasi website yang sama dengan halaman lain disisipkan (tema /shared/theme.css + lonceng notifikasi).
# Folder arsip/ tidak disalin. Jalankan ulang setiap kali modul di docs/modules/ berubah:  bash scripts/sync_modules.sh
set -euo pipefail
cd "$(dirname "$0")/.."
src=docs/modules
dst=web/static/modules
mkdir -p "$dst"
for f in "$src"/merakit-node-*.html; do
  out="$dst/$(basename "$f")"
  python3 - "$f" "$out" <<'PY'
import re, sys
src, out = sys.argv[1], sys.argv[2]
s = open(src, encoding="utf-8").read()
s = re.sub(r'<link[^>]+fonts\.(googleapis|gstatic)\.com[^>]*>\n?', "", s)
head = ('<link rel="icon" href="/product/airlens-icon.svg" type="image/svg+xml">\n'
        '<link rel="stylesheet" href="/shared/theme.css?v=20261123">\n<link rel="stylesheet" href="/shared/alerts.css?v=20261123">\n'
        '<style>nav.toc { top: 73px !important; max-height: calc(100vh - 89px) !important; } '
        'section { scroll-margin-top: 80px !important; } .wrap { max-width: calc(var(--page) + 32px) !important; }</style>\n')
s = s.replace("<style>", head + "<style>", 1)
bar = ('<header class="bar">\n  <a class="brand" href="/"><img src="/product/airlens-icon.svg" alt="" width="28" height="28"><span>AirLens</span></a>\n'
       '  <nav class="site-nav" aria-label="AirLens pages"><ul>\n    <li><a href="/">Photo demo</a></li>\n'
       '    <li><a href="/beta.html">Beta sensor</a></li>\n    <li><a href="/product.html">Product</a></li>\n'
       '    <li><a href="/modules/" aria-current="page">Build guides</a></li>\n  </ul></nav>\n</header>\n')
# modul ditulis tanpa <head>/<body> eksplisit: kepala disisipkan tepat setelah </style> pertama milik modul
i = s.index("</style>", s.index(head) + len(head)) + len("</style>")
s = s[:i] + "\n" + bar + s[i:] + '\n<script src="/shared/alerts.js?v=20261123"></script>\n'

open(out, "w", encoding="utf-8").write(s)
PY
  if grep -qE 'fonts\.(googleapis|gstatic)\.com' "$out"; then
    echo "GAGAL: $out masih memuat tautan Google Fonts" >&2
    exit 1
  fi
  echo "disalin: $f -> $out"
done
