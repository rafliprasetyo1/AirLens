#!/usr/bin/env bash
# Seluruh alur lab dalam satu perintah (Tahap 4). Urutan mendahulukan dua model utama, lalu langsung dikemas:
#   cek -> layanan -> migrasi -> data (foto + gas Beta) -> latih model foto AQI 3 tingkat -> latih model gas Beta
#   -> evaluasi AQI -> KEMAS (arsip pertama) -> [referensi 5 kelas -> compare_merge] -> KEMAS ulang (arsip final)
# Tahap utama berantai: bila satu gagal, tahap utama berikutnya dilewati, tetapi hasil yang ada TETAP dikemas.
# Tahap opsional (referensi 5 kelas, compare_merge) tidak pernah menggagalkan alur.
# Saklar darurat (variabel lingkungan): SKIP_CHECK=1, SKIP_BETA=1 (lewati model gas Beta), SKIP_COMPARE=1 (lewati
# referensi 5 kelas + compare_merge), SKIP_BETA_DATA=1 (lewati unduhan data gas Beta).
# Durasi tiap tahap: logs/lab_<waktu>/timings.tsv. Ringkasan (termasuk bagian yang dilewati): RINGKASAN.txt.
# Pemakaian: scripts/lab_all.sh laptop|lab   (dipanggil oleh `make lab-all`; SMOKE=1 = uji asap cepat)
set -uo pipefail
PROFILE="${1:-laptop}"
SMOKE="${SMOKE:-0}"
LOG="logs/lab_$(date +%Y%m%d_%H%M%S)_${PROFILE}"
mkdir -p "$LOG"
COMPOSE=(docker compose -f compose.yaml)
[ "$PROFILE" = lab ] && COMPOSE+=(-f compose.gpu.yaml)
printf 'tahap\tmulai\tselesai\tdetik\tstatus\tdisk_terpakai_GB\tdata_GB\tdocker_images_GB\n' > "$LOG/timings.tsv"
SKIPPED=()

disk_used() { df -BG --output=used . | tail -1 | tr -dc '0-9'; }
size_gb() { du -sk "$1" 2>/dev/null | awk '{printf "%.2f", $1/1048576}' || echo 0; }
docker_gb() { docker system df --format '{{.Type}} {{.Size}}' 2>/dev/null | awk '$1=="Images"{print $2}'; }

FAILED=""
record() {  # record <nama> <mulai> <detik> <status>
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$1" "$2" "$(date -Iseconds)" "$3" "$4" \
    "$(disk_used)" "$(size_gb data)" "$(docker_gb)" >> "$LOG/timings.tsv"
}
run() {  # run <nama> <perintah...>: jalankan dan catat; mengembalikan kode keluar perintah
  local name="$1"; shift
  echo; echo "== $name: mulai $(date +%H:%M:%S)"
  local t0 s0 rc
  t0=$(date +%s); s0=$(date -Iseconds)
  "$@" 2>&1 | tee "$LOG/${name}.log"
  rc=${PIPESTATUS[0]}
  local secs=$(( $(date +%s) - t0 )) status=ok
  [ "$rc" -ne 0 ] && status="gagal($rc)"
  record "$name" "$s0" "$secs" "$status"
  echo "== $name: $status dalam $((secs / 60)) mnt $((secs % 60)) dtk"
  return "$rc"
}
stage() {  # tahap utama berantai
  local name="$1"
  if [ -n "$FAILED" ]; then
    printf '%s\t-\t-\t0\tdilewati\t-\t-\t-\n' "$name" >> "$LOG/timings.tsv"
    echo "== $name: DILEWATI (tahap $FAILED gagal)"; SKIPPED+=("$name (tahap $FAILED gagal)"); return
  fi
  run "$@" || FAILED="$name"
}
optional() {  # tahap opsional: gagal dicatat, alur jalan terus
  local name="$1"
  run "$@" || SKIPPED+=("$name GAGAL (opsional, lihat $LOG/$name.log)")
}
skip() { printf '%s\t-\t-\t0\tdilewati(%s)\t-\t-\t-\n' "$1" "$2" >> "$LOG/timings.tsv"; echo "== $1: DILEWATI ($2)"; SKIPPED+=("$1 ($2)"); }

summary() {  # tulis RINGKASAN.txt (dipanggil sebelum setiap kemas agar ikut masuk arsip, dan di akhir)
  {
    echo "Ringkasan lab-all $(date -Iseconds) · profil $PROFILE · SMOKE=$SMOKE"
    column -t -s $'\t' "$LOG/timings.tsv" 2>/dev/null || cat "$LOG/timings.tsv"
    echo
    [ -n "$MAIN_FAILED" ] && echo "STATUS: tahap utama '$MAIN_FAILED' GAGAL — lihat $LOG/${MAIN_FAILED}.log" \
      || echo "STATUS: model foto AQI tiga tingkat + model gas Beta selesai dan terkemas"
    if [ ${#SKIPPED[@]} -gt 0 ]; then echo "Dilewati / gagal:"; printf '  - %s\n' "${SKIPPED[@]}"; fi
    echo
    python3 - <<'PY' 2>/dev/null || true
import json, pathlib
r = pathlib.Path("results")
s = r / "beta_final.json"
if s.exists():
    d = json.loads(s.read_text()); t = d.get("test") or {}
    print(f"Model gas Beta v{d['version']}: test macro-F1 {t.get('macro_f1', 0):.3f}, recall asap {t.get('recall_smoke', 0):.3f}")
c = r / "compare_merge_3class.md"
if c.exists():
    print("compare_merge (5 kelas digabung vs 3 tingkat, test yang sama):")
    print(c.read_text())
PY
    ls -t results/airlens_results_"${PROFILE}"_*.tar.gz 2>/dev/null | head -1 | sed 's/^/Arsip: /'
  } > "$LOG/RINGKASAN.txt"
}

echo "AirLens lab-all (profil $PROFILE, SMOKE=$SMOKE) — log: $LOG"
[ "${SKIP_CHECK:-0}" = 1 ] && skip setup-check SKIP_CHECK=1 || stage setup-check scripts/setup_check.sh "$PROFILE"
stage layanan "${COMPOSE[@]}" up -d --wait db mlflow
stage migrasi make migrate PROFILE="$PROFILE"
stage data make data PROFILE="$PROFILE" ${SKIP_BETA_DATA:+SKIP_BETA_DATA=1}
stage train make train PROFILE="$PROFILE" SMOKE="$SMOKE"
if [ "${SKIP_BETA:-0}" = 1 ]; then skip train-beta SKIP_BETA=1
else stage train-beta make train-beta PROFILE="$PROFILE"; fi
stage eval make eval PROFILE="$PROFILE" SMOKE="$SMOKE"
MAIN_FAILED="$FAILED"

# Kemas hasil utama SELALU dijalankan, juga bila ada tahap yang gagal: dua model utama aman lebih dulu.
summary
run export-utama scripts/export_results.sh "$PROFILE" || SKIPPED+=("export-utama GAGAL")

if [ "${SKIP_COMPARE:-0}" = 1 ]; then
  skip train-referensi-5kelas SKIP_COMPARE=1; skip compare-merge SKIP_COMPARE=1
elif [ -n "$MAIN_FAILED" ]; then
  skip train-referensi-5kelas "tahap utama $MAIN_FAILED gagal"; skip compare-merge "tahap utama $MAIN_FAILED gagal"
else
  ARCH="$(docker compose -f compose.yaml --profile train run --rm -T trainer python -c "
from airlens.config import load_profile; from airlens.data.manifest import read_data_version
from airlens.data.paths import processed_dir; from airlens.models.bundle import read_candidates
print(read_candidates(read_data_version(processed_dir(load_profile()['profile'])))['production'])" 2>/dev/null | tail -1)"
  if optional train-referensi-5kelas make train PROFILE="$PROFILE" SMOKE="$SMOKE" TRAIN_CLASS_SCHEME=epa5 TRAIN_MODELS="$ARCH"; then
    optional compare-merge make compare-merge PROFILE="$PROFILE"
  else
    skip compare-merge "referensi 5 kelas gagal"
  fi
  summary
  run export-final scripts/export_results.sh "$PROFILE" || SKIPPED+=("export-final GAGAL")
fi

summary
cat "$LOG/RINGKASAN.txt"
[ -z "$MAIN_FAILED" ]
