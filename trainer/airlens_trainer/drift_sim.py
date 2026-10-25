"""`make drift-sim`: buktikan peringatan drift menyala pada input yang bergeser dan TIDAK menyala pada input normal.

Foto set test dikirim lewat API sungguhan (alur utama lengkap, tercatat di db) dalam tiga gelombang:
  1. normal      : foto test PM25Vision asli (lokasi baru, domain sama dengan data latih) -> tidak boleh menyala
  2. bergeser    : foto yang sama, digelapkan + dikaburkan (kamera buram / mendung / malam) -> harus menyala
  3. domain baru : foto test Biratnagar (satu kamera, kabut tebal; domain berbeda) -> diharapkan menyala
Biratnagar sengaja TIDAK dipakai sebagai kontrol normal: pemeriksaan menunjukkan domainnya memang bergeser di semua
fitur (lihat DECISIONS.md).
Setelah tiap gelombang, job monitoring yang sama dengan job terjadwal dijalankan pada jendela waktu gelombang itu,
dengan referensi dari model production. Catatan: prediksi simulasi tetap tercatat di db pengembangan.
"""

import io
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from PIL import Image, ImageEnhance, ImageFilter

from airlens.config import load_profile
from airlens.data.paths import RESULTS_DIR
from airlens.db.session import get_engine
from airlens.models import registry
from airlens.models.data import Dataset, load_dataset
from airlens.monitoring.job import run as run_monitoring

API = os.environ.get("AIRLENS_API_URL", "http://api:8000")
N = int(os.environ.get("DRIFT_SIM_N", "60"))
logger = logging.getLogger("airlens.drift_sim")


def as_jpeg(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def shift(path: str) -> bytes:
    img = Image.open(path).convert("RGB")
    img = ImageEnhance.Brightness(img).enhance(0.6)
    return as_jpeg(img.filter(ImageFilter.GaussianBlur(radius=max(2, min(img.size) // 120))))


def send(payloads: list[bytes]) -> list[str]:
    statuses = []
    for data in payloads:
        job = requests.post(f"{API}/predict", files={"file": ("sim.jpg", data, "image/jpeg")}, timeout=30).json()["job_id"]
        for _ in range(300):
            body = requests.get(f"{API}/jobs/{job}", timeout=10).json()
            if body["done"]:
                statuses.append(body["result"]["status"])
                break
            time.sleep(0.1)
    return statuses


def wave(name: str, payloads: list[bytes], cfg: dict, reference: dict) -> dict:
    start = datetime.now(timezone.utc)
    statuses = send(payloads)
    end = datetime.now(timezone.utc)
    rep = run_monitoring(get_engine(), cfg, Path("/nonexistent"), RESULTS_DIR / "monitoring", since=start, until=end,
                         reference=reference, report_type=f"simulasi-{name}")
    drift = [a for a in rep["alerts"] if a["type"] == "drift"]
    print(f"\n=== gelombang {name}: {len(payloads)} foto, status {dict((s, statuses.count(s)) for s in set(statuses))}")
    print(f"peringatan: {[a['message'] for a in rep['alerts'] if a['type'] != 'info'] or 'tidak ada'}")
    print(f"laporan: {rep['markdown']}")
    return {"n": len(payloads), "drift_alerts": len(drift), "alerts": rep["alerts"], "markdown": rep["markdown"],
            "psi": {k: v["psi"] for k, v in rep["drift"].items()}}


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    cfg = load_profile()
    ds = load_dataset(cfg["profile"], cfg["data"]["class_merge"])
    test = ds.split("test")
    pv = test[test["source"] == "pm25vision"]
    pv = pv.sample(n=min(N, len(pv)), random_state=cfg["data"]["seed"])
    paths = [Dataset.abs_path(p) for p in pv["image_path"]]
    other = [Dataset.abs_path(p) for p in test[test["source"] != "pm25vision"]["image_path"]]
    prod_v = registry.alias_version("production")
    reference = json.loads((registry.download_bundle(prod_v, "/tmp/airlens-registry") / "metadata.json").read_text())
    if not reference.get("monitoring_reference"):
        print(f"Model production v{prod_v} belum punya monitoring_reference; latih ulang dengan kode Fase 5.")
        return 1
    normal = wave("normal", [as_jpeg(Image.open(p).convert("RGB")) for p in paths], cfg, reference)
    shifted = wave("bergeser", [shift(p) for p in paths], cfg, reference)
    domain = wave("domain-baru", [as_jpeg(Image.open(p).convert("RGB")) for p in other], cfg, reference) if other else None
    verdict = normal["drift_alerts"] == 0 and shifted["drift_alerts"] > 0
    print(f"\nHASIL: normal {normal['drift_alerts']} peringatan drift, bergeser {shifted['drift_alerts']}, domain baru "
          f"{domain['drift_alerts'] if domain else '-'} -> {'TERBUKTI' if verdict else 'TIDAK SESUAI HARAPAN'}")
    (RESULTS_DIR / "monitoring" / "drift_sim.json").write_text(json.dumps(
        {"production": prod_v, "n": len(paths), "normal": normal, "bergeser": shifted, "domain_baru": domain,
         "terbukti": verdict},
        indent=2, ensure_ascii=False, default=str))
    return 0 if verdict else 2


if __name__ == "__main__":
    sys.exit(main())
