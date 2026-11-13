#!/usr/bin/env bash
# Kemas semua hasil menjadi SATU arsip bertanggal: results/airlens_results_<profil>_<waktu>.tar.gz
# Isi: results/ (eval, grafik, laporan), artifacts/models (bundle ONNX), log lab, ringkasan data, volume artefak
# MLflow, dump database mlflow + airlens, info lingkungan, dan MANIFEST sha256. TIDAK PERNAH memuat .env.
# Pemakaian: scripts/export_results.sh laptop|lab    (dipanggil oleh `make export-results`)
set -euo pipefail
PROFILE="${1:-laptop}"
PROJECT="${COMPOSE_PROJECT_NAME:-airlens}"
ALPINE_IMAGE="alpine:3.24.3"
TS="$(date +%Y%m%d_%H%M%S)"
NAME="airlens_results_${PROFILE}_${TS}"
STAGE="$(mktemp -d)"
OUT="$STAGE/$NAME"
mkdir -p "$OUT"
trap 'rm -rf "$STAGE"' EXIT
compose() { docker compose -p "$PROJECT" -f compose.yaml "$@"; }

echo "Mengemas hasil ke results/${NAME}.tar.gz"

# 1. Berkas di repo (tanpa arsip lama, tanpa fixture uji UI)
tar -cf - --exclude='results/airlens_results_*' --exclude='results/ui' results 2>/dev/null | tar -xf - -C "$OUT" || true
[ -d artifacts/models ] && { mkdir -p "$OUT/artifacts"; cp -r artifacts/models "$OUT/artifacts/"; }
[ -d logs ] && cp -r logs "$OUT/"
if [ -d "data/processed/$PROFILE" ]; then
  mkdir -p "$OUT/data_summary"
  for f in report.json manifest.csv data_version.txt; do
    [ -f "data/processed/$PROFILE/$f" ] && cp "data/processed/$PROFILE/$f" "$OUT/data_summary/"
  done
fi

# 2. Volume artefak MLflow (model terdaftar, grafik, metadata run)
if docker volume inspect "${PROJECT}_mlartifacts" >/dev/null 2>&1; then
  docker run --rm -v "${PROJECT}_mlartifacts:/v:ro" -v "$OUT:/out" "$ALPINE_IMAGE" \
    sh -c 'tar -czf /out/mlartifacts.tar.gz -C /v . && chown '"$(id -u):$(id -g)"' /out/mlartifacts.tar.gz'
else
  echo "PERINGATAN: volume ${PROJECT}_mlartifacts tidak ada; artefak MLflow tidak ikut" | tee "$OUT/PERINGATAN_mlartifacts.txt"
fi

# 3. Dump database (riwayat run + registry MLflow; log prediksi, riwayat model, laporan monitoring)
compose up -d --wait db >/dev/null 2>&1 || true
for db in mlflow airlens; do
  if compose exec -T db sh -c "pg_dump -U \"\$POSTGRES_USER\" --no-owner $db" > "$OUT/${db}_db.sql" 2>"$OUT/${db}_db.err"; then
    rm -f "$OUT/${db}_db.err"
  else
    echo "PERINGATAN: dump database $db gagal (lihat ${db}_db.err)"
  fi
done

# 4. Info lingkungan (tanpa rahasia)
{
  echo "profil: $PROFILE"
  echo "waktu: $(date -Iseconds)"
  echo "git: $(git rev-parse --short HEAD 2>/dev/null || echo -)$(git diff --quiet HEAD 2>/dev/null || echo ' (ada perubahan belum di-commit)')"
  echo "docker: $(docker version --format '{{.Server.Version}}' 2>/dev/null) / $(docker info --format '{{.OperatingSystem}}' 2>/dev/null)"
  echo "gpu: $( (nvidia-smi -L 2>/dev/null || /usr/lib/wsl/lib/nvidia-smi -L 2>/dev/null) | head -1 || echo tidak terdeteksi)"
  echo "data_version: $(cat "data/processed/$PROFILE/data_version.txt" 2>/dev/null || echo -)"
} > "$OUT/ENVIRONMENT.txt"

# 5. Pastikan tidak ada rahasia yang ikut
if [ -f .env ]; then
  for k in POSTGRES_PASSWORD IQAIR_API_KEY KAGGLE_KEY MAPILLARY_ACCESS_TOKEN OPENAQ_API_KEY; do
    v="$(grep -E "^$k=" .env | tail -1 | cut -d= -f2- || true)"
    [ -n "$v" ] && grep -rlF -- "$v" "$OUT" >/dev/null 2>&1 && { echo "BATAL: nilai $k ditemukan di arsip"; exit 3; }
  done
fi
find "$OUT" -name '.env' -delete

# 6. Manifest + arsip
( cd "$OUT" && find . -type f ! -name MANIFEST.sha256 -print0 | sort -z | xargs -0 sha256sum > MANIFEST.sha256 )
mkdir -p results
tar -czf "results/${NAME}.tar.gz" -C "$STAGE" "$NAME"
echo "Selesai: results/${NAME}.tar.gz ($(du -h "results/${NAME}.tar.gz" | cut -f1))"
for f in mlflow_db.sql airlens_db.sql mlartifacts.tar.gz; do
  [ -s "$OUT/$f" ] && echo "  ada  $f ($(du -h "$OUT/$f" | cut -f1))" || echo "  TIDAK ADA / KOSONG  $f"
done
