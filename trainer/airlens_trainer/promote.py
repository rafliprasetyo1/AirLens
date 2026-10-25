"""`make promote`: bandingkan challenger vs production lalu promosikan HANYA bila semua kriteria config terpenuhi.

Pembanding: (1) set TEST tetap dari data saat ini, dievaluasi lewat ONNX dengan temperatur dan ambang masing-masing
model; (2) data shadow di db (foto pengguna yang sama, diprediksi kedua model). Laporan: results/promotion_<waktu>.md.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from airlens.config import load_profile
from airlens.data.paths import RESULTS_DIR
from airlens.db.models import Prediction
from airlens.db.session import get_engine
from airlens.models import registry
from airlens.models.bundle import onnx_logits
from airlens.models.calibration import calibrated_probs
from airlens.models.data import Dataset, load_dataset
from airlens.models.metrics import classification_metrics, expected_calibration_error, selective_metrics

logger = logging.getLogger("airlens.promote")
CACHE = Path("/tmp/airlens-registry")


def evaluate(bundle: Path, paths: list[str], y: np.ndarray) -> dict:
    meta = json.loads((bundle / "metadata.json").read_text())
    onnx = next(bundle.rglob("*.onnx"))
    probs = calibrated_probs(onnx_logits(onnx, paths), meta["temperature"])
    m = classification_metrics(y, probs.argmax(1), len(meta["classes"]))
    sel = selective_metrics(probs, y, meta["threshold"]["threshold"], len(meta["classes"]))
    return {"macro_f1": round(m["macro_f1"], 4), "balanced_accuracy": round(m["balanced_accuracy"], 4),
            "ece": round(expected_calibration_error(probs, y), 4), "rejected_fraction": round(sel["rejected_fraction"], 4),
            "data_version": meta["data_version"], "smoke": meta.get("smoke", False), "name": meta["name"]}


def shadow_stats(engine, prod_v: str, ch_v: str) -> dict:
    with Session(engine) as s:
        prod = {r.job_id: r for r in s.scalars(select(Prediction).where(
            Prediction.is_shadow.is_(False), Prediction.model_version == f"{registry.REGISTERED_MODEL}/{prod_v}",
            Prediction.status.in_(("ok", "uncertain"))))}
        ch = [r for r in s.scalars(select(Prediction).where(
            Prediction.is_shadow.is_(True), Prediction.model_version == f"{registry.REGISTERED_MODEL}/{ch_v}"))
            if r.job_id in prod]
    n = len(ch)
    if not n:
        return {"n": 0}
    return {"n": n,
            "sepakat_kelas": round(sum(prod[r.job_id].predicted_class == r.predicted_class for r in ch) / n, 4),
            "belum_pasti_production": round(sum(prod[r.job_id].status == "uncertain" for r in ch) / n, 4),
            "belum_pasti_challenger": round(sum(r.status == "uncertain" for r in ch) / n, 4)}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    cfg = load_profile()
    crit = cfg["promotion"]
    engine = get_engine()
    prod_v, ch_v = registry.alias_version("production"), registry.alias_version("challenger")
    if not ch_v:
        print("Tidak ada challenger. Jalankan `make retrain` dulu.")
        return 1
    if not prod_v:
        print("Belum ada production. Jalankan `make train` dulu.")
        return 1

    ds = load_dataset(cfg["profile"], cfg["data"]["class_merge"])
    test = ds.split("test")
    paths, y = [Dataset.abs_path(p) for p in test["image_path"]], test["y"].to_numpy()
    res = {name: evaluate(registry.download_bundle(v, CACHE), paths, y) for name, v in (("production", prod_v), ("challenger", ch_v))}
    sh = shadow_stats(engine, prod_v, ch_v)
    p, c = res["production"], res["challenger"]
    checks = [
        ("Test tetap sesuai data challenger (tanpa kebocoran)", c["data_version"] == ds.data_version,
         f"data challenger {c['data_version'][:12]} vs data sekarang {ds.data_version[:12]}"),
        (f"macro-F1 test challenger >= production + {crit['min_macro_f1_gain']}",
         c["macro_f1"] >= p["macro_f1"] + crit["min_macro_f1_gain"], f"{c['macro_f1']} vs {p['macro_f1']}"),
        (f"ECE challenger <= production + {crit['max_ece_increase']}", c["ece"] <= p["ece"] + crit["max_ece_increase"],
         f"{c['ece']} vs {p['ece']}"),
        (f"Sampel shadow >= {crit['min_shadow_samples']}", sh["n"] >= crit["min_shadow_samples"], f"n = {sh['n']}"),
        (f"'Belum pasti' di shadow naik <= {crit['max_uncertain_rate_increase']}",
         sh["n"] > 0 and sh["belum_pasti_challenger"] - sh["belum_pasti_production"] <= crit["max_uncertain_rate_increase"],
         f"{sh.get('belum_pasti_challenger')} vs {sh.get('belum_pasti_production')}"),
    ]
    ok = all(passed for _, passed, _ in checks)
    now = datetime.now(timezone.utc)
    lines = [f"# Keputusan promosi model — {now:%Y-%m-%d %H:%M} UTC", "",
             f"Production v{prod_v} ({p['name']}) vs challenger v{ch_v} ({c['name']}) · test {len(y)} gambar · shadow {sh['n']}",
             "", "| Metrik test | production | challenger |", "|---|---:|---:|"]
    lines += [f"| {k} | {p[k]} | {c[k]} |" for k in ("macro_f1", "balanced_accuracy", "ece", "rejected_fraction")]
    lines += ["", f"Shadow: {json.dumps(sh, ensure_ascii=False)}", "", "| Kriteria | Hasil | Detail |", "|---|---|---|"]
    lines += [f"| {name} | {'✅' if passed else '❌'} | {detail} |" for name, passed, detail in checks]
    if p["smoke"] or c["smoke"]:
        lines += ["", "> Salah satu model adalah model uji asap (SMOKE); angka ini hanya membuktikan alur."]
    if ok:
        previous = registry.set_production(engine, ch_v)
        registry.clear_challenger()
        lines += ["", f"**DIPROMOSIKAN**: production v{previous} → v{ch_v}. Alias challenger dihapus. "
                      "API memuat model baru otomatis (≤ 30 detik). Rollback: `make rollback`."]
    else:
        lines += ["", "**DITOLAK**: kriteria belum terpenuhi; production tidak berubah, challenger tetap berjalan di shadow."]
    out = RESULTS_DIR / f"promotion_{now:%Y%m%d_%H%M%S}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nLaporan: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
