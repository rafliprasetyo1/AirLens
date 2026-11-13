#!/usr/bin/env bash
# Seluruh alur dalam satu perintah: cek lingkungan -> db+mlflow -> migrasi skema -> data -> latih -> evaluasi -> kemas.
# Durasi dan pemakaian disk tiap tahap dicatat di logs/lab_<waktu>/timings.tsv (sumber perkiraan waktu di README).
# Bila satu tahap gagal, tahap berikutnya dilewati, tetapi hasil yang sudah ada TETAP dikemas.
# Pemakaian: scripts/lab_all.sh laptop|lab   (dipanggil oleh `make lab-all`; SMOKE=1 = uji asap cepat)
set -uo pipefail
PROFILE="${1:-laptop}"
SMOKE="${SMOKE:-0}"
LOG="logs/lab_$(date +%Y%m%d_%H%M%S)_${PROFILE}"
mkdir -p "$LOG"
COMPOSE=(docker compose -f compose.yaml)
[ "$PROFILE" = lab ] && COMPOSE+=(-f compose.gpu.yaml)
printf 'tahap\tmulai\tselesai\tdetik\tstatus\tdisk_terpakai_GB\tdata_GB\tdocker_images_GB\n' > "$LOG/timings.tsv"

disk_used() { df -BG --output=used . | tail -1 | tr -dc '0-9'; }
size_gb() { du -sk "$1" 2>/dev/null | awk '{printf "%.2f", $1/1048576}' || echo 0; }
docker_gb() { docker system df --format '{{.Type}} {{.Size}}' 2>/dev/null | awk '$1=="Images"{print $2}'; }

FAILED=""
run_stage() {  # run_stage <nama> <perintah...>
  local name="$1"; shift
  if [ -n "$FAILED" ]; then
    printf '%s\t-\t-\t0\tdilewati\t-\t-\t-\n' "$name" >> "$LOG/timings.tsv"
    echo "== $name: DILEWATI (tahap $FAILED gagal)"
    return
  fi
  echo; echo "== $name: mulai $(date +%H:%M:%S)"
  local t0 s0 rc
  t0=$(date +%s); s0=$(date -Iseconds)
  "$@" 2>&1 | tee "$LOG/${name}.log"
  rc=${PIPESTATUS[0]}
  local secs=$(( $(date +%s) - t0 ))
  local status=ok; [ "$rc" -ne 0 ] && { status="gagal($rc)"; FAILED="$name"; }
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$name" "$s0" "$(date -Iseconds)" "$secs" "$status" \
    "$(disk_used)" "$(size_gb data)" "$(docker_gb)" >> "$LOG/timings.tsv"
  echo "== $name: $status dalam $((secs / 60)) mnt $((secs % 60)) dtk"
}

echo "AirLens lab-all (profil $PROFILE, SMOKE=$SMOKE) — log: $LOG"
if [ "${SKIP_CHECK:-0}" = 1 ]; then
  echo "== setup-check dilewati (SKIP_CHECK=1)"
else
  run_stage setup-check scripts/setup_check.sh "$PROFILE"
fi
run_stage layanan "${COMPOSE[@]}" up -d --wait db mlflow
run_stage migrasi make migrate PROFILE="$PROFILE"
run_stage data make data PROFILE="$PROFILE"
run_stage train make train PROFILE="$PROFILE" SMOKE="$SMOKE"
run_stage eval make eval PROFILE="$PROFILE" SMOKE="$SMOKE"

# Kemas hasil SELALU dijalankan, juga bila ada tahap yang gagal.
FAILED_BEFORE="$FAILED"; FAILED=""
run_stage export scripts/export_results.sh "$PROFILE"

{
  echo "Ringkasan lab-all $(date -Iseconds) · profil $PROFILE · SMOKE=$SMOKE"
  column -t -s $'\t' "$LOG/timings.tsv" 2>/dev/null || cat "$LOG/timings.tsv"
  [ -n "$FAILED_BEFORE" ] && echo "STATUS: tahap '$FAILED_BEFORE' GAGAL — lihat $LOG/${FAILED_BEFORE}.log" || echo "STATUS: semua tahap selesai"
} | tee "$LOG/RINGKASAN.txt"
[ -z "$FAILED_BEFORE" ] && [ -z "$FAILED" ]
