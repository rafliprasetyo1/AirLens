"""`make train PROFILE=...`: latih baseline + CNN, kalibrasi dan ambang di VALIDASI, catat ke MLflow, daftarkan model.

`make train` mendaftarkan model terbaik sebagai production; `make retrain` (REGISTER_ALIAS=challenger) sebagai
challenger yang dijalankan API dalam shadow mode sampai `make promote`.

Test TIDAK dipakai di sini sama sekali; evaluasi test ada di eval.py.
Model production = model yang bisa di-deploy (CNN/ONNX) dengan macro-F1 validasi tertinggi. Bila baseline lebih
tinggi di validasi, hal itu dicatat dan dilaporkan, bukan disembunyikan.
"""

import json
import logging
import os
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone

import joblib
import mlflow
import numpy as np
import torch

from airlens.config import load_profile
from airlens.features.haze import HINTS, hint_values
from airlens.models import baseline, cnn
from airlens.models.bundle import features_cache, load_metadata, models_dir, save_metadata, write_candidates
from airlens.models.calibration import calibrated_probs, choose_threshold, fit_temperature
from airlens.models.data import Dataset, load_dataset
from airlens.models.metrics import classification_metrics, expected_calibration_error, selective_metrics
from airlens.db.session import get_engine
from airlens.models import registry
from airlens.models.preprocess import SPEC, load_image, preprocess
from airlens.monitoring.signature import FEATURES, fit_pca, input_signature, project
from airlens.versioning import apply_smoke, code_version, git_commit, is_smoke

logger = logging.getLogger("airlens.train")
REGISTERED_MODEL = registry.REGISTERED_MODEL
MONITOR_SAMPLE = 2000


def _signature(path: str) -> dict:
    return input_signature(load_image(path))  # decode penuh: jalur sama dengan API


def monitoring_reference(onnx_path, paths: list[str], seed: int, workers: int) -> dict:
    """Referensi drift dari data LATIH: fitur gambar + proyeksi PCA embedding (sampel maks MONITOR_SAMPLE)."""
    import onnxruntime as ort

    rng = np.random.default_rng(seed)
    sample = [paths[i] for i in sorted(rng.choice(len(paths), min(MONITOR_SAMPLE, len(paths)), replace=False))]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        sigs = list(ex.map(_signature, sample, chunksize=16))
    sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    emb = np.concatenate([sess.run(["embedding"], {"image": np.concatenate([preprocess(p) for p in sample[i:i + 32]])})[0]
                          for i in range(0, len(sample), 32)])
    pca = fit_pca(emb)
    proj = project(emb, pca)
    return {"n": len(sample), "features": {f: [round(float(s[f]), 5) for s in sigs] for f in FEATURES},
            "emb_pca": pca, "emb_proj": {f"emb_pc{i + 1}": proj[:, i].round(5).tolist() for i in range(proj.shape[1])}}


def calibrate_and_score(logits: np.ndarray, y: np.ndarray, n_classes: int, cal_cfg: dict) -> dict:
    temperature = fit_temperature(logits, y)
    probs = calibrated_probs(logits, temperature)
    thr = choose_threshold(probs, y, cal_cfg["target_accuracy"], cal_cfg["min_accepted"])
    m = classification_metrics(y, probs.argmax(1), n_classes)
    return {
        "temperature": temperature,
        "threshold": thr,
        "val": {
            **{k: m[k] for k in ("accuracy", "balanced_accuracy", "macro_f1", "recall_per_class")},
            "ece_before": expected_calibration_error(calibrated_probs(logits, 1.0), y),
            "ece": expected_calibration_error(probs, y),
            **selective_metrics(probs, y, thr["threshold"], n_classes),
        },
    }


def _log_common(meta: dict, cal: dict, classes: list[str]) -> None:
    mlflow.set_tags({**{k: meta[k] for k in ("data_version", "code_version", "git_commit", "profile", "kind")},
                     "smoke": str(meta["smoke"]).lower()})
    mlflow.log_params({f"param_{k}": v for k, v in meta.get("params", {}).items()})
    v = cal["val"]
    mlflow.log_metrics({
        "val_balanced_accuracy": v["balanced_accuracy"], "val_macro_f1": v["macro_f1"], "val_accuracy": v["accuracy"],
        "val_ece_before": v["ece_before"], "val_ece": v["ece"], "temperature": cal["temperature"],
        "threshold": cal["threshold"]["threshold"], "val_rejected_fraction": v["rejected_fraction"],
        "val_accepted_accuracy": v["accepted_accuracy"],
        **{f"val_recall_{c}": r for c, r in zip(classes, v["recall_per_class"])},
    })


def load_metadata_of(bundle_dir: str) -> dict:
    from pathlib import Path

    return load_metadata(Path(bundle_dir))


def run(profile_name: str | None = None) -> dict:
    cfg = load_profile(profile_name)
    profile, tcfg, cal_cfg, seed = cfg["profile"], apply_smoke(cfg["training"]), cfg["calibration"], cfg["data"]["seed"]
    ds: Dataset = load_dataset(profile, cfg["data"]["class_merge"])
    tr, va = ds.split("train"), ds.split("val")
    n_classes = len(ds.classes)
    out_root = models_dir(ds.data_version)
    common = {"data_version": ds.data_version, "code_version": code_version(), "git_commit": git_commit(),
              "profile": profile, "classes": ds.classes, "seed": seed, "smoke": is_smoke()}
    logger.info("data %s: train %d, val %d, kelas %s", ds.data_version[:12], len(tr), len(va), ds.classes)
    mlflow.set_experiment("airlens-train")
    candidates: dict = {"data_version": ds.data_version, "models": {}}

    # ---------------------------------------------------------------- baseline
    all_df = ds.frame
    feats = baseline.feature_table([Dataset.abs_path(p) for p in all_df["image_path"]], list(all_df["image_path"]),
                                   features_cache(ds.data_version), workers=tcfg["num_workers"])
    x_tr, x_va = feats.loc[tr["image_path"]].to_numpy(), feats.loc[va["image_path"]].to_numpy()
    # Sebaran fitur petunjuk visual di data latih (kuantil 0..100 tiap 5%), dipakai API untuk membandingkan foto pengguna.
    hints_tr = feats.loc[tr["image_path"]].apply(hint_values, axis=1, result_type="expand")
    hint_reference = {f: np.quantile(hints_tr[f], np.linspace(0, 1, 21)).round(5).tolist() for f in HINTS}
    fitted = baseline.fit_baselines(x_tr, tr["y"].to_numpy(), x_va, va["y"].to_numpy(), n_classes, seed)
    for name, info in fitted.items():
        logits = baseline.logits_from_proba(info["model"], x_va, n_classes)
        cal = calibrate_and_score(logits, va["y"].to_numpy(), n_classes, cal_cfg)
        bundle_dir = out_root / name
        with mlflow.start_run(run_name=f"{name}-{profile}") as r:
            meta = {**common, "name": name, "kind": "sklearn", "deployable": False, "params": info["params"],
                    "temperature": cal["temperature"], "threshold": cal["threshold"], "val_metrics": cal["val"],
                    "features": "airlens.features.haze.FEATURE_NAMES", "mlflow_run_id": r.info.run_id,
                    "created_at": datetime.now(timezone.utc).isoformat()}
            _log_common(meta, cal, ds.classes)
            bundle_dir.mkdir(parents=True, exist_ok=True)
            joblib.dump(info["model"], bundle_dir / "model.joblib")
            save_metadata(bundle_dir, meta)
            mlflow.log_artifacts(str(bundle_dir), artifact_path="bundle")
        candidates["models"][name] = {"dir": str(bundle_dir), "kind": "sklearn", "val_macro_f1": cal["val"]["macro_f1"],
                                      "mlflow_run_id": meta["mlflow_run_id"]}
        logger.info("%s: val macro-F1 %.4f, ECE %.3f -> %.3f", name, cal["val"]["macro_f1"], cal["val"]["ece_before"],
                    cal["val"]["ece"])

    # ---------------------------------------------------------------- CNN
    torch.set_num_threads(tcfg["threads"])
    device = "cuda" if tcfg["device"] == "cuda" and torch.cuda.is_available() else "cpu"
    if tcfg["device"] == "cuda" and device == "cpu":
        logger.warning("profil meminta GPU tetapi CUDA tidak tersedia; melatih di CPU")
    tr_paths, va_paths = [Dataset.abs_path(p) for p in tr["image_path"]], [Dataset.abs_path(p) for p in va["image_path"]]
    for arch in tcfg["models"]:
        bundle_dir = out_root / arch
        with mlflow.start_run(run_name=f"{arch}-{profile}") as r:
            hp = {k: tcfg[k] for k in ("batch_size", "epochs_head", "epochs_full", "lr_head", "lr_full",
                                        "weight_decay", "patience")}
            model, hist = cnn.train_cnn(arch, tr_paths, list(tr["y"]), va_paths, list(va["y"]), n_classes, tcfg, seed,
                                        device, on_epoch=lambda h: mlflow.log_metrics(
                                            {"epoch_train_loss": h["train_loss"], "epoch_val_macro_f1": h["val_macro_f1"]},
                                            step=h["epoch"]))
            logits = cnn.val_logits(model, va_paths, list(va["y"]), tcfg, seed)
            cal = calibrate_and_score(logits, va["y"].to_numpy(), n_classes, cal_cfg)
            onnx_diff = cnn.export_onnx(model, bundle_dir / "model.onnx", va_paths[0])
            torch.save(model.state_dict(), bundle_dir / "model.pt")
            mon_ref = monitoring_reference(bundle_dir / "model.onnx", tr_paths, seed, tcfg["num_workers"])
            meta = {**common, "name": arch, "kind": "onnx", "deployable": True, "params": {**hp, "arch": arch},
                    "device": device, "temperature": cal["temperature"], "threshold": cal["threshold"],
                    "val_metrics": cal["val"], "preprocessing": SPEC, "onnx_max_abs_diff": onnx_diff,
                    "hint_reference": hint_reference, "monitoring_reference": mon_ref,
                    "best_epoch": hist["best_epoch"], "history": hist["history"], "mlflow_run_id": r.info.run_id,
                    "created_at": datetime.now(timezone.utc).isoformat()}
            _log_common(meta, cal, ds.classes)
            mlflow.log_metrics({"onnx_max_abs_diff": onnx_diff, "best_epoch": hist["best_epoch"]})
            save_metadata(bundle_dir, meta)
            import onnx

            info = mlflow.onnx.log_model(onnx.load(str(bundle_dir / "model.onnx")), name="model",
                                         metadata={k: meta[k] for k in ("classes", "temperature", "data_version",
                                                                        "code_version", "preprocessing")})
            mlflow.log_artifact(str(bundle_dir / "metadata.json"), artifact_path="bundle")
        if onnx_diff > 1e-3:
            raise RuntimeError(f"{arch}: keluaran ONNX berbeda dari PyTorch (maks {onnx_diff:.2e})")
        candidates["models"][arch] = {"dir": str(bundle_dir), "kind": "onnx", "val_macro_f1": cal["val"]["macro_f1"],
                                      "mlflow_run_id": meta["mlflow_run_id"], "model_uri": info.model_uri}
        logger.info("%s: val macro-F1 %.4f (epoch %d), ECE %.3f -> %.3f, ambang %.3f (target tercapai: %s), ONNX diff %.1e",
                    arch, cal["val"]["macro_f1"], hist["best_epoch"], cal["val"]["ece_before"], cal["val"]["ece"],
                    cal["threshold"]["threshold"], cal["threshold"]["target_tercapai"], onnx_diff)

    # ---------------------------------------------------------------- pilih dan daftarkan
    deployable = {n: c for n, c in candidates["models"].items() if c["kind"] == "onnx"}
    best = max(deployable, key=lambda n: deployable[n]["val_macro_f1"])
    overall = max(candidates["models"], key=lambda n: candidates["models"][n]["val_macro_f1"])
    alias = os.environ.get("REGISTER_ALIAS", "production")
    mv = mlflow.register_model(deployable[best]["model_uri"], REGISTERED_MODEL,
                               tags={"data_version": ds.data_version, "bundle": best, "smoke": str(is_smoke()).lower()})
    engine = get_engine()
    registry.record_registration(engine, mv.version, "candidate", load_metadata_of(deployable[best]["dir"]))
    if alias == "challenger":
        registry.set_challenger(engine, mv.version)
    else:
        registry.set_production(engine, mv.version)
    candidates.update({"smoke": is_smoke(), "production": best, "production_registry_version": mv.version, "alias": alias,
                       "best_overall_on_val": overall, "registered_model": REGISTERED_MODEL})
    write_candidates(ds.data_version, candidates)
    if overall != best:
        logger.warning("baseline %s mengungguli CNN terbaik di validasi; production tetap %s (satu-satunya yang bisa "
                       "di-deploy). Dilaporkan di eval.", overall, best)
    logger.info("%s: %s (registry %s v%s)", alias, best, REGISTERED_MODEL, mv.version)
    return candidates


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    result = run()
    print(json.dumps({n: round(c["val_macro_f1"], 4) for n, c in result["models"].items()}, indent=2))
    print(f"{result['alias']}:", result["production"], "| registry versi", result["production_registry_version"])


if __name__ == "__main__":
    main()
