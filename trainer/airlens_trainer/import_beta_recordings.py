"""`make import-beta-recordings CSV=<path> [RETRAIN=1] [WEIGHT=3]`: rekaman alat Beta sendiri (tools/recorder.html).

1. Fitur rekaman dihitung persis seperti di API: Rs dari mV pin, baseline = median Rs baris berlabel clean_air di
   rekaman itu, fitur = Rs/R0 + MQ-3/MQ-2.
2. Domain shift: model production dievaluasi pada semua baris berlabel, lalu dibandingkan dengan metrik test dataset
   publiknya. Selisih macro-F1 = seberapa jauh model turun di alat sendiri.
3. RETRAIN=1 (dijalankan kernel Kaggle, bukan di laptop): latih ulang dengan data latih dataset publik + bagian latih rekaman (bobot WEIGHT, bawaan 3), split
   rekaman per label menurut waktu (70% awal latih, 30% akhir uji, 15 baris purge). Model baru didaftarkan sebagai
   **challenger** hanya bila macro-F1 di bagian uji rekaman lebih baik daripada production DAN macro-F1 test dataset
   publik tidak turun lebih dari 0,05. Promosi tetap lewat `make promote-beta` (atau shadow di API).
Laporan: results/beta_recordings_<waktu>.md + .json.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from airlens.config import load_profile
from airlens.data.beta_gas import class_names, device_features, feature_names, load_beta_config, rs_from_mv
from airlens.data.manifest import read_data_version
from airlens.data.paths import RESULTS_DIR, processed_dir
from airlens.models import registry
from airlens.models.bundle import ARTIFACTS_DIR

MV = {"MQ2": "mq2_mv", "MQ3": "mq3_mv", "MQ7": "mq7_mv", "MQ135": "mq135_mv"}
MIN_CLEAN_ROWS = 10
MAX_DATASET_DROP = 0.05


def read_recording(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = {"timestamp", "label", *MV.values()} - set(df.columns)
    if missing:
        raise ValueError(f"{path.name}: kolom tidak ada: {sorted(missing)} (pakai CSV dari tools/recorder.html)")
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["recording"] = path.name
    return df


def recording_features(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Fitur per baris; baseline = median Rs baris clean_air rekaman yang sama. Baris tanpa label/tidak valid dibuang."""
    valid = df[list(MV.values())].gt(0).all(axis=1) & df[list(MV.values())].lt(3300).all(axis=1)
    clean = df[valid & (df["label"] == "clean_air")]
    if len(clean) < MIN_CLEAN_ROWS:
        raise ValueError(f"{df['recording'].iloc[0]}: butuh >= {MIN_CLEAN_ROWS} baris 'Clean air' untuk baseline "
                         f"(ada {len(clean)})")
    baseline = {s: float(np.median([rs_from_mv(v) for v in clean[c]])) for s, c in MV.items()}
    rows = df[valid & df["label"].isin(class_names(cfg))].copy()
    feats = [device_features({s: r[c] for s, c in MV.items()}, baseline, cfg) for _, r in rows.iterrows()]
    out = pd.concat([rows.reset_index(drop=True), pd.DataFrame(feats)], axis=1)
    out.attrs["baseline_rs"] = baseline
    return out


def recording_split(df: pd.DataFrame, train_frac: float = 0.7, purge: int = 15) -> pd.Series:
    """Per (rekaman, label), urut waktu: awal -> train, akhir -> test, baris di sekitar batas dibuang ('')."""
    split = pd.Series("", index=df.index, dtype=object)
    for _, g in df.groupby(["recording", "label"], sort=False):
        idx = list(g.index)
        cut = int(round(len(idx) * train_frac))
        for i, row in enumerate(idx):
            if i < cut - purge:
                split[row] = "train"
            elif i >= cut + purge:
                split[row] = "test"
    return split


def predict(booster, x: pd.DataFrame, feats: list[str]) -> np.ndarray:
    return booster.predict(x[feats].to_numpy(dtype=float), raw_score=True).argmax(1)


def main() -> int:
    from airlens_trainer.promote_beta import load_booster
    from airlens_trainer.train_beta import log_and_register, metrics, plots, train

    profile, cfg = load_profile()["profile"], load_beta_config()
    feats, classes, name = feature_names(cfg), class_names(cfg), cfg["registered_model"]
    paths = [Path(p) for p in os.environ.get("CSVS", "").split(",") if p.strip()]
    if not paths:
        print("Tidak ada CSV. Pakai: make import-beta-recordings CSV=<path ke CSV recorder>")
        return 1
    rec = pd.concat([recording_features(read_recording(p), cfg) for p in paths], ignore_index=True)
    y_rec = np.array([classes.index(v) for v in rec["label"]])
    prod_v = registry.alias_version("production", model=name)
    if not prod_v:
        print(f"Belum ada production {name}; jalankan make train-beta dulu.")
        return 1
    bundle = registry.download_bundle(prod_v, ARTIFACTS_DIR / "registry-cache", model=name)
    prod_meta = json.loads((bundle / "metadata.json").read_text())
    prod = load_booster(bundle)
    shift = metrics(y_rec, predict(prod, rec, feats), classes)
    dataset_f1 = (prod_meta.get("test_metrics") or {}).get("macro_f1")
    report = {"recordings": [p.name for p in paths], "rows": int(len(rec)),
              "rows_per_label": rec["label"].value_counts().to_dict(), "production_version": prod_v,
              "production_on_recordings": shift, "production_dataset_test_macro_f1": dataset_f1,
              "macro_f1_drop": (dataset_f1 - shift["macro_f1"]) if dataset_f1 is not None else None}
    lines = [f"# Rekaman alat Beta: {', '.join(p.name for p in paths)}", "",
             f"{len(rec)} baris berlabel: {report['rows_per_label']}", "",
             "## Domain shift (model production pada rekaman alat sendiri)", "",
             f"- Production v{prod_v}: macro-F1 dataset publik (test) {dataset_f1:.3f} → rekaman alat {shift['macro_f1']:.3f}"
             if dataset_f1 is not None else f"- Production v{prod_v}: macro-F1 rekaman {shift['macro_f1']:.3f}",
             f"- F1 per kelas di rekaman: {json.dumps({k: round(v, 3) for k, v in shift['f1'].items()})}",
             f"- Confusion matrix (baris = label, kolom = prediksi, urutan {classes}): {shift['confusion_matrix']}"]

    if os.environ.get("RETRAIN") == "1":
        weight = float(os.environ.get("WEIGHT", "3"))
        rec["split"] = recording_split(rec)
        tr, te = rec[rec["split"] == "train"], rec[rec["split"] == "test"]
        if tr.empty or te.empty:
            print("Rekaman terlalu pendek untuk dibagi latih/uji (butuh beberapa menit per label).")
            return 1
        data_dir = processed_dir(profile) / "beta_gas"
        table = pd.read_csv(data_dir / "features.csv")
        y_tr, y_te = np.array([classes.index(v) for v in tr["label"]]), np.array([classes.index(v) for v in te["label"]])
        booster, xs, ys, _ = train(cfg, table, extra=(tr[feats].to_numpy(dtype=float), y_tr, np.full(len(y_tr), weight)))
        ds_test = table[table["split"] == "test"]
        y_ds = np.array([classes.index(v) for v in ds_test["label"]])
        new_rec, old_rec = metrics(y_te, predict(booster, te, feats), classes), metrics(y_te, predict(prod, te, feats), classes)
        new_ds, old_ds = metrics(y_ds, predict(booster, ds_test, feats), classes), metrics(y_ds, predict(prod, ds_test, feats), classes)
        better = new_rec["macro_f1"] > old_rec["macro_f1"] and new_ds["macro_f1"] >= old_ds["macro_f1"] - MAX_DATASET_DROP
        report["retrain"] = {"weight": weight, "rows_train": int(len(tr)), "rows_test": int(len(te)),
                             "new_on_recording_test": new_rec, "production_on_recording_test": old_rec,
                             "new_on_dataset_test": new_ds, "production_on_dataset_test": old_ds, "registered": better}
        lines += ["", f"## Latih ulang (dataset publik + rekaman, bobot {weight:g})", "",
                  f"- Uji rekaman ({len(te)} baris): baru {new_rec['macro_f1']:.3f} vs production {old_rec['macro_f1']:.3f}",
                  f"- Test dataset publik: baru {new_ds['macro_f1']:.3f} vs production {old_ds['macro_f1']:.3f}"]
        if better:
            rec_hash = hashlib.sha256(b"".join(p.read_bytes() for p in paths)).hexdigest()
            data_version = hashlib.sha256((read_data_version(data_dir) + rec_hash).encode()).hexdigest()
            out = ARTIFACTS_DIR / "models" / "beta_gas" / data_version[:12] / "lightgbm"
            out.mkdir(parents=True, exist_ok=True)
            booster.save_model(str(out / "model.txt"))
            extra = plots(booster, xs["test"], ys["test"], predict(booster, ds_test, feats), feats, classes, out / "plots")
            meta = {**{k: prod_meta[k] for k in ("classes", "features", "sensors", "clean_air_reference_adc",
                                                 "dataset_citation", "registered_model") if k in prod_meta},
                    "name": "lightgbm", "kind": "lightgbm", "task": "beta_gas", "data_version": data_version,
                    "profile": profile, "params": cfg["model"], "val_metrics": new_rec, "test_metrics": new_ds,
                    "recording_test_metrics": new_rec, "recordings": [p.name for p in paths], "recording_weight": weight,
                    **extra}
            mv = log_and_register(cfg, booster, out, meta, {"recording_test_macro_f1": new_rec["macro_f1"],
                                                            "test_macro_f1": new_ds["macro_f1"]},
                                  "challenger", f"beta-gas-recordings-{profile}")
            report["retrain"]["version"] = mv.version
            if os.environ.get("PROMOTE_IF_BETTER") == "1":   # kernel Kaggle: model gabungan menjadi model final
                from airlens.db.session import get_engine

                registry.set_production(get_engine(), mv.version, model=name)
                (RESULTS_DIR / "beta_final.json").write_text(json.dumps(
                    {"bundle": str(out), "version": mv.version, "source": "dataset publik + rekaman alat",
                     "test_recording": new_rec, "test_dataset": new_ds}, indent=2) + "\n")
            lines += ["", f"**Didaftarkan sebagai challenger v{mv.version}.** API menjalankannya dalam shadow; "
                          "promosi dengan `make promote-beta`."]
        else:
            lines += ["", "**Tidak didaftarkan**: model baru tidak lebih baik di rekaman, atau turun di dataset publik."]

    now = datetime.now(timezone.utc)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stem = RESULTS_DIR / f"beta_recordings_{now:%Y%m%d_%H%M%S}"
    stem.with_suffix(".md").write_text("\n".join(lines) + "\n")
    stem.with_suffix(".json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
