"""`make eval PROFILE=...`: evaluasi semua model kandidat di TEST (dan val untuk pembanding) memakai temperatur dan
ambang yang sudah dikunci di validasi. Hasil: results/eval_<tanggal>.csv + grafik di results/eval_<tanggal>/.

Model CNN dievaluasi lewat ONNX (sama persis dengan yang akan dipakai API).
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd

from airlens.config import load_profile
from airlens.data.paths import RESULTS_DIR
from airlens.models import plots, vlm
from airlens.models.bundle import bundle_logits, features_cache, load_metadata, read_candidates
from airlens.models.calibration import calibrated_probs
from airlens.models.data import Dataset, load_dataset
from airlens.versioning import is_smoke
from airlens.models.metrics import (
    classification_metrics,
    expected_calibration_error,
    reliability_bins,
    risk_coverage,
    selective_metrics,
)

logger = logging.getLogger("airlens.eval")


def score(probs: np.ndarray, y: np.ndarray, threshold: float, classes: list[str]) -> dict:
    m = classification_metrics(y, probs.argmax(1), len(classes))
    sel = selective_metrics(probs, y, threshold, len(classes))
    return {
        "n": int(len(y)), "accuracy": m["accuracy"], "balanced_accuracy": m["balanced_accuracy"],
        "macro_f1": m["macro_f1"], "ece": expected_calibration_error(probs, y), **sel,
        **{f"recall_{c}": r for c, r in zip(classes, m["recall_per_class"])},
        "confusion_matrix": json.dumps(m["confusion_matrix"]),
    }


def run(profile_name: str | None = None) -> pd.DataFrame:
    cfg = load_profile(profile_name)
    profile = cfg["profile"]
    ds = load_dataset(profile, cfg["data"]["class_merge"])
    cands = read_candidates(ds.data_version)
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    if cands.get("smoke") or is_smoke():
        today += "_smoke"  # uji asap: jangan tertukar dengan hasil evaluasi sungguhan
    fig_dir = RESULTS_DIR / f"eval_{today}"
    feats = pd.read_parquet(features_cache(ds.data_version)).set_index("image_path")
    splits = {s: ds.split(s) for s in ("val", "test")}
    rows, curves, operating, production_probs = [], {}, {}, None

    for name, cand in cands["models"].items():
        bdir = Path(cand["dir"])
        meta = load_metadata(bdir)
        thr = meta["threshold"]["threshold"]
        for split, df in splits.items():
            paths = [Dataset.abs_path(p) for p in df["image_path"]]
            logits = bundle_logits(bdir, paths, feats.loc[df["image_path"]].to_numpy() if meta["kind"] == "sklearn" else None)
            probs = calibrated_probs(logits, meta["temperature"])
            y = df["y"].to_numpy()
            rows.append({"model": name, "split": split, "is_production": name == cands["production"],
                         "kind": meta["kind"], "temperature": meta["temperature"], **score(probs, y, thr, ds.classes)})
            if split != "test":
                continue
            # Rincian per sumber (mis. pm25vision vs india_nepal vs dhaka) untuk melihat pergeseran domain.
            for src, idx in df.groupby("source").groups.items():
                idx = np.asarray(idx)
                rows.append({"model": name, "split": f"test:{src}", "is_production": name == cands["production"],
                             "kind": meta["kind"], "temperature": meta["temperature"],
                             **score(probs[idx], y[idx], thr, ds.classes)})
            m = classification_metrics(y, probs.argmax(1), len(ds.classes))
            plots.confusion_matrix_plot(m["confusion_matrix"], ds.classes, f"{name} - test", fig_dir / f"cm_{name}.png")
            plots.reliability_plot(reliability_bins(probs, y), expected_calibration_error(probs, y),
                                   f"{name} - test (setelah temperature scaling)", fig_dir / f"reliability_{name}.png")
            cov, acc, _ = risk_coverage(probs, y)
            curves[name] = (cov, acc)
            sel = selective_metrics(probs, y, thr, len(ds.classes))
            operating[name] = (1 - sel["rejected_fraction"], sel["accepted_accuracy"])
            if name == cands["production"]:
                production_probs = probs
    plots.risk_coverage_plot(curves, operating, "Risiko-cakupan di test", fig_dir / "risk_coverage.png")

    # ---------------------------------------------------------------- VLM (opsional)
    test = splits["test"]
    n_max = cfg["vlm"]["max_images"]
    sub = test if not n_max or n_max >= len(test) else test.sample(n=n_max, random_state=cfg["data"]["seed"])
    res = vlm.classify([Dataset.abs_path(p) for p in sub["image_path"]], ds.classes)
    vlm_info = {"status": res["status"], "reason": res["reason"], "model": res["model"],
                "device": os.environ.get("VLM_DEVICE", "tidak diketahui (LM Studio di Windows)")}
    if res["status"] == "ok":
        y = sub["y"].to_numpy()
        pred = np.array([ds.classes.index(p) if p else -1 for p in res["predictions"]])
        valid = pred >= 0
        m = classification_metrics(y[valid], pred[valid], len(ds.classes))
        rows.append({"model": f"vlm:{res['model']}", "split": "test_subset", "is_production": False, "kind": "vlm",
                     "n": int(len(y)), "accuracy": m["accuracy"], "balanced_accuracy": m["balanced_accuracy"],
                     "macro_f1": m["macro_f1"], "rejected_fraction": float(1 - valid.mean()),
                     "seconds_per_image": float(np.mean(res["seconds"])),
                     **{f"recall_{c}": r for c, r in zip(ds.classes, m["recall_per_class"])},
                     "confusion_matrix": json.dumps(m["confusion_matrix"])})
        # Model production pada subset yang sama, agar perbandingannya adil.
        pp = production_probs[test.index.get_indexer(sub.index)]
        rows.append({"model": cands["production"], "split": "test_subset", "is_production": True, "kind": "onnx",
                     **score(pp, y, load_metadata(Path(cands["models"][cands["production"]]["dir"]))["threshold"]["threshold"],
                             ds.classes)})
    vlm_info["n_images"] = int(len(sub)) if res["status"] == "ok" else 0

    out = pd.DataFrame(rows)
    out.insert(0, "data_version", ds.data_version)
    out.insert(1, "profile", profile)
    out["evaluated_at"] = datetime.now(timezone.utc).isoformat()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv = RESULTS_DIR / f"eval_{today}.csv"
    out.to_csv(csv, index=False)
    (fig_dir / "vlm.json").write_text(json.dumps(vlm_info, indent=2, ensure_ascii=False))
    (fig_dir / "indonesia.json").write_text(json.dumps(
        {"status": "dilewati", "reason": "set uji Indonesia belum dibuat (Fase 2b opsional)"}, ensure_ascii=False))

    # Metrik test ke run MLflow masing-masing model.
    for name, cand in cands["models"].items():
        r = out[(out["model"] == name) & (out["split"] == "test")].iloc[0]
        with mlflow.start_run(run_id=cand["mlflow_run_id"]):
            mlflow.log_metrics({f"test_{k}": float(r[k]) for k in ("balanced_accuracy", "macro_f1", "accuracy", "ece",
                                                                   "rejected_fraction", "accepted_accuracy")
                                if pd.notna(r[k])})
            for f in fig_dir.glob(f"*_{name}.png"):
                mlflow.log_artifact(str(f), artifact_path="eval")
            mlflow.set_tag("evaluated_at", out["evaluated_at"].iloc[0])
    logger.info("hasil: %s, grafik: %s, VLM: %s", csv, fig_dir, vlm_info["status"])
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    out = run()
    cols = ["model", "split", "n", "balanced_accuracy", "macro_f1", "ece", "threshold", "rejected_fraction",
            "accepted_accuracy"]
    view = out[out["split"].isin(["val", "test", "test_subset"]) | out["split"].str.startswith("test:")]
    print(view[[c for c in cols if c in view]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
