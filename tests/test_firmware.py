"""Firmware Beta dan proyek Wokwi: HTTPS ke ngrok tanpa setInsecure, header wajib, pin ADC1, rahasia tidak
ada di kode, sertifikat akar, sketch Wokwi identik dengan firmware, dan manifest .bin cocok dengan berkasnya."""

import hashlib
import json
import re
from pathlib import Path

import pytest

ROOT = Path("/app") if Path("/app/firmware").exists() else Path(__file__).resolve().parents[1]
BETA = ROOT / "firmware" / "beta" / "beta.ino"


@pytest.mark.parametrize("path", [BETA])
def test_https_with_root_ca_and_required_headers(path):
    code = path.read_text()
    code_only = "\n".join(line.split("//")[0] for line in code.splitlines())   # tanpa komentar
    assert "setInsecure" not in code_only
    assert "setCACert(AIRLENS_ROOT_CAS)" in code and '#include "airlens_roots.h"' in code
    assert '"ngrok-skip-browser-warning", "1"' in code and '"X-Node-Token"' in code
    assert 'Preferences' in code and 'prefs.getString("url"' in code and 'prefs.getString("token"' in code
    # tidak ada rahasia/URL tertanam: tidak ada string ngrok domain atau kata sandi di kode
    assert not re.search(r'https://[a-z0-9-]+\.ngrok', code)
    assert "configTime(" in code   # jam NTP sebelum validasi sertifikat


def test_beta_reads_four_adc1_pins_every_two_seconds():
    code = BETA.read_text()
    assert "PIN_MQ2 = 34, PIN_MQ3 = 35, PIN_MQ7 = 32, PIN_MQ135 = 33" in code
    assert "analogReadMilliVolts" in code and "periodMs = 2000" in code
    for field in ("mq2_mv", "mq3_mv", "mq7_mv", "mq135_mv", "node_id", "uptime_s"):
        assert f'\\"{field}\\"' in code
    # password tidak pernah dicetak ke Serial
    assert "has_pass" in code and "pass.c_str()" not in code.split("void printSettings")[1].split("}\n")[0]


def test_root_header_contains_all_certs():
    pems = sorted((ROOT / "firmware" / "certs").glob("*.pem"))
    assert {p.stem for p in pems} == {"isrg_root_x1", "isrg_root_x2", "isrg_root_ye"}
    for sketch in ("firmware/beta", "wokwi/beta"):
        header = (ROOT / sketch / "airlens_roots.h").read_text()
        assert header.count("BEGIN CERTIFICATE") == 3
        for p in pems:   # baris base64 pertama tiap sertifikat ada di header
            first = p.read_text().splitlines()[1]
            assert first in header


def test_wokwi_sketch_identical_and_diagram_wired_like_device():
    assert (ROOT / "wokwi" / "beta" / "sketch.ino").read_text() == BETA.read_text()
    d = json.loads((ROOT / "wokwi" / "beta" / "diagram.json").read_text())
    parts = {p["id"]: p for p in d["parts"]}
    gas = [p for p in d["parts"] if p["type"] == "wokwi-gas-sensor"]
    assert len(gas) == 4
    links = {(a, b) for a, b, *_ in d["connections"]} | {(b, a) for a, b, *_ in d["connections"]}
    # Wokwi tidak menyimulasikan resistor bersama komponen analog (docs.wokwi.com/parts/wokwi-resistor): dengan pembagi
    # 10k/20k, pin ADC membaca angka tetap berapa pun ppm-nya. Di simulasi AOUT langsung ke GPIO; alat asli WAJIB
    # memakai pembagi (5 V -> ±3,3 V), lihat panduan perakitan dan hardware/README.md.
    assert not [p for p in d["parts"] if p["type"] == "wokwi-resistor"]
    for sid, pin in (("mq2", "34"), ("mq3", "35"), ("mq7", "32"), ("mq135", "33")):
        assert (f"{sid}:AOUT", f"esp:{pin}") in links
        assert (f"{sid}:VCC", "esp:5V") in links
        assert parts[f"{sid}_label"]["attrs"]["text"].startswith("MQ-")


def test_firmware_manifest_matches_binaries():
    out = ROOT / "web" / "static" / "tools" / "firmware"
    if not (out / "manifest.json").exists():
        pytest.skip("firmware belum dikompilasi (make firmware-beta)")
    m = json.loads((out / "manifest.json").read_text())
    for name, f in m["files"].items():
        data = (out / f["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == f["sha256"] and len(data) == f["bytes"]
        # ESP32 klasik: bootloader di 0x1000 (berkas gabungan di-flash di 0x0, 4 KB pertama berisi 0xFF)
        assert data[0x1000] == 0xE9 and set(data[:0x1000]) == {0xFF}
