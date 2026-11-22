#!/usr/bin/env bash
# `make firmware-beta`: kompilasi firmware Beta (ESP32 DevKit + 4 MQ) dengan arduino-cli,
# lalu salin .bin gabungan (bootloader + partisi + aplikasi, flash di offset 0x0) ke web/static/tools/firmware/
# agar bisa di-flash dari browser (tools/flash.html). Toolchain hanya dibutuhkan di laptop; .bin hasil ikut di-commit
# supaya komputer lab cukup membuka halaman flash.
#
# Pemasangan sekali (tanpa sudo, ±1,5 GB): lihat firmware/README.md.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
CORE="esp32:esp32@3.3.13"
if [ -z "${ROOTS_ONLY:-}" ]; then
  command -v arduino-cli >/dev/null || { echo "arduino-cli belum terpasang; lihat firmware/README.md" >&2; exit 1; }
  arduino-cli core list | grep -q "^esp32:esp32 *3.3.13" || { echo "core $CORE belum terpasang: arduino-cli core install $CORE" >&2; exit 1; }
fi

# 1) Sertifikat akar -> header C (satu string PEM berisi beberapa akar; mbedTLS menerima semuanya)
python3 - <<'PY'
from pathlib import Path
pems = sorted(Path("firmware/certs").glob("*.pem"))
body = "".join(p.read_text().strip() + "\n" for p in pems)
lines = "\n".join(f'"{l}\\n"' for l in body.strip().splitlines())
names = ", ".join(p.stem for p in pems)
header = ("// DIBUAT OTOMATIS oleh scripts/firmware_build.sh dari firmware/certs/*.pem. Jangan diedit manual.\n"
          f"// Akar Let's Encrypt untuk domain ngrok (*.ngrok-free.app / *.ngrok-free.dev): {names}.\n"
          "#pragma once\nstatic const char AIRLENS_ROOT_CAS[] =\n" + lines + ";\n")
for sketch in ("firmware/beta", "wokwi/beta"):
    Path(sketch, "airlens_roots.h").write_text(header)
print(f"airlens_roots.h: {len(pems)} akar ({names})")
PY

# Modul perakitan menampilkan kode lengkap firmware: sisipkan isi beta.ino terbaru (blok <script id="c3">)
python3 - <<'PY'
from pathlib import Path
p = Path("docs/modules/merakit-node-lite.html")
s = p.read_text()
start = s.index('<script type="text/plain" id="c3">') + len('<script type="text/plain" id="c3">')
end = s.index("</script>", start)
fw = Path("firmware/beta/beta.ino").read_text().rstrip("\n")
new = s[:start] + fw + s[end:]
# penjelasan "Baris X–Y" tiap fungsi mengikuti kode terbaru (dulu bergeser setiap firmware berubah)
import re
src = fw.split("\n")
for m in re.finditer(r'<b>Baris [0-9]+–[0-9]+</b><span><code>(\w+)</code>', new):
    name = m.group(1)
    i = next((k for k, l in enumerate(src) if re.match(rf"\w[\w<>]* {name}\(", l)), None)
    if i is None:
        continue
    j = next(k for k in range(i, len(src)) if src[k].startswith("}"))
    new = new.replace(m.group(0), f'<b>Baris {i + 1}–{j + 1}</b><span><code>{name}</code>', 1)
if new != s:
    p.write_text(new)
    print("modul perakitan: kode firmware dan nomor baris penjelasan diperbarui (jalankan make sync-modules)")
PY

[ -n "${ROOTS_ONLY:-}" ] && { cp firmware/beta/beta.ino wokwi/beta/sketch.ino; exit 0; }

# Proyek Wokwi memakai sketch yang sama persis dengan firmware Beta (tes memeriksa keduanya identik)
cp firmware/beta/beta.ino wokwi/beta/sketch.ino

OUT=web/static/tools/firmware
mkdir -p "$OUT" build/firmware
build() {   # build <sketch> <fqbn> <nama .bin>
  local sketch=$1 fqbn=$2 name=$3
  arduino-cli compile --fqbn "$fqbn" --output-dir "build/firmware/$name" "$sketch"
  # .bin gabungan diisi 0xFF sampai 4 MB; isian di belakang aplikasi dipangkas (dibulatkan ke 4 KB) agar berkas kecil
  python3 - "build/firmware/$name/$(basename "$sketch").ino.merged.bin" "$OUT/$name.bin" <<'PY'
import sys
data = open(sys.argv[1], "rb").read()
end = len(data.rstrip(b"\xff"))
end = (end + 4095) // 4096 * 4096
open(sys.argv[2], "wb").write(data[:end])
print(f"{sys.argv[2]}: {end} dari {len(data)} byte")
PY
}
build firmware/beta "esp32:esp32:esp32" beta

python3 - "$OUT" <<'PY'
import hashlib, json, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
out = Path(sys.argv[1])
def fw(sketch):
    m = re.search(r'#define FW_VERSION "([^"]+)"', Path(f"firmware/{sketch}/{sketch}.ino").read_text())
    return m.group(1)
commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
manifest = {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "core": "esp32:esp32@3.3.13",
            "git_commit": commit, "offset": "0x0", "baud": 115200, "files": {}}
for name in ("beta",):
    data = (out / f"{name}.bin").read_bytes()
    manifest["files"][name] = {"file": f"{name}.bin", "version": fw(name), "bytes": len(data),
                               "sha256": hashlib.sha256(data).hexdigest(),
                               "board": "ESP32 DevKit (ESP32-WROOM-32)"}
(out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
for k, v in manifest["files"].items():
    print(f"{k}: {v['file']} {v['bytes']} byte, sha256 {v['sha256'][:12]}…, {v['version']}")
PY
