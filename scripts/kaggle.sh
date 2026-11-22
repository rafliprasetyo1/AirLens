#!/usr/bin/env bash
# `make kaggle-push | kaggle-status | kaggle-pull` (prompt 7). Menyiapkan build/kaggle/ di host (kode dari working tree +
# kernel), lalu menjalankan Kaggle CLI di container trainer (kredensial dari .env, tidak dicetak).
set -euo pipefail
cd "$(dirname "$0")/.."
cmd="${1:?push|status|pull|prepare|recordings}"
mkdir -p build/kaggle/code build/kaggle/kernel results
if [ "$cmd" = push ] || [ "$cmd" = prepare ]; then
  commit="$(git rev-parse --short HEAD 2>/dev/null || echo belum-ada-commit)$(git diff --quiet HEAD 2>/dev/null || echo -dirty)"
  printf '{"git_commit": "%s", "created": "%s"}\n' "$commit" "$(date -Iseconds)" > build/kaggle/CODE_INFO.json
  # hanya kode yang dibutuhkan pelatihan (tanpa data, artefak, web, dokumen besar)
  git ls-files -co --exclude-standard -- src api trainer scheduler config scripts kaggle requirements Makefile \
    | while read -r f; do if [ -f "$f" ]; then echo "$f"; fi; done \
    | tar -cf build/kaggle/code/airlens_code.tar --transform 's,^,AirLens/,' -T -
  tar -rf build/kaggle/code/airlens_code.tar -C build/kaggle --transform 's,^,AirLens/,' CODE_INFO.json
  gzip -f build/kaggle/code/airlens_code.tar
  cp build/kaggle/CODE_INFO.json build/kaggle/code/CODE_INFO.json
  cp kaggle/kernel/run.py build/kaggle/kernel/run.py
  echo "kode $commit: $(du -h build/kaggle/code/airlens_code.tar.gz | cut -f1)"
fi
[ "$cmd" = prepare ] && exit 0
docker compose -f compose.yaml --profile train run --rm --build -T -v "$PWD/build/kaggle:/kaggle_build" \
  trainer python -m airlens_trainer.kaggle_ops "$cmd"
