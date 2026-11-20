"""Pembanding adil untuk keputusan 3 kelas (2026-11-20): model 5 kelas LAMA, probabilitasnya dijumlahkan per kelas
gabungan, dinilai pada split val/test yang SAMA dengan model 3 kelas baru.

Memisahkan dua efek: (a) kenaikan karena tugasnya lebih mudah (penggabungan saja) vs (b) kenaikan karena retrain.
Ambang model lama disetel ulang di VALIDASI dengan aturan yang sama (config calibration), tidak pernah di test.

  python -m airlens_trainer.compare_merge <bundle_lama> <bundle_baru>
"""

import json
import sys
from pathlib import Path

import numpy as np

from airlens.aqi import merge_for_classes
from airlens.config import load_profile
from airlens.data.paths import RESULTS_DIR
from airlens.models.bundle import onnx_logits
from airlens.models.calibration import calibrated_probs, choose_threshold
from airlens.models.data import Dataset, load_dataset
from airlens.models.metrics import classification_metrics, expected_calibration_error, selective_metrics


def probs_on(bundle: Path, frame, classes: list[str]) -> np.ndarray:
    """Probabilitas terkalibrasi bundle, dipetakan ke `classes` (kelas asal dijumlahkan ke kelas gabungannya)."""
    meta = json.loads((bundle / "metadata.json").read_text())
    p = calibrated_probs(onnx_logits(bundle / "model.onnx", [Dataset.abs_path(x) for x in frame["image_path"]]),
                         meta["temperature"])
    target = merge_for_classes(classes)
    out = np.zeros((len(p), len(classes)))
    for j, c in enumerate(meta["classes"]):
        out[:, classes.index(target.get(c, c))] += p[:, j]
    return out


def main() -> int:
    old, new = Path(sys.argv[1]), Path(sys.argv[2])
    cfg = load_profile()
    ds = load_dataset(cfg["profile"], cfg["data"]["class_merge"])
    k, cal = len(ds.classes), cfg["calibration"]
    rows = []
    for name, bundle in (("5 kelas lama, digabung", old), ("3 kelas, dilatih ulang", new)):
        va, te = ds.split("val"), ds.split("test")
        pv, pt = probs_on(bundle, va, ds.classes), probs_on(bundle, te, ds.classes)
        th = choose_threshold(pv, va["y"].to_numpy(), cal["target_accuracy"], cal["min_accepted"])
        for split, frame, p in (("test", te, pt), *((f"test:{s}", te[te["source"] == s], pt[(te["source"] == s).to_numpy()])
                                                   for s in sorted(te["source"].unique()))):
            y = frame["y"].to_numpy()
            m = classification_metrics(y, p.argmax(1), k)
            sel = selective_metrics(p, y, th["threshold"], k)
            rows.append({"model": name, "split": split, "n": len(y), "accuracy": round(m["accuracy"], 4),
                         "balanced_accuracy": round(m["balanced_accuracy"], 4), "macro_f1": round(m["macro_f1"], 4),
                         "ece": round(expected_calibration_error(p, y), 4), "threshold_val": round(th["threshold"], 4),
                         "target_tercapai_val": th["target_tercapai"], "coverage": round(1 - sel["rejected_fraction"], 4),
                         "accepted_accuracy": None if np.isnan(sel["accepted_accuracy"]) else round(sel["accepted_accuracy"], 4)})
    out = RESULTS_DIR / "compare_merge_3class.json"
    out.write_text(json.dumps({"data_version": ds.data_version, "classes": ds.classes, "rows": rows}, indent=2,
                              ensure_ascii=False))
    for r in rows:
        print(r)
    print(f"Laporan: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
