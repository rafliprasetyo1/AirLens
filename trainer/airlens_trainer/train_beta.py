"""`make train-beta`: model gas Beta (`airlens-beta-gas`) dari empat MQ, dijelaskan dengan SHAP.

Data: processed/<profil>/beta_gas (dari `make data-beta`). Model: LightGBM multikelas kecil (CPU, hitungan detik),
berhenti dini di validasi. Kenapa LightGBM: TreeSHAP persis tersedia bawaan (`pred_contrib`), sehingga API bisa
menjelaskan setiap bacaan tanpa memuat pustaka `shap` (yang hanya dipakai di sini untuk plot global dan pemeriksaan
silang). Nilai SHAP berada di ruang skor mentah (log-odds softmax) per kelas: nilai dasar + jumlah SHAP = skor kelas.

Keluaran: model.txt (LightGBM), metadata.json (kelas, fitur, referensi udara bersih dataset, nilai dasar, metrik),
plot SHAP global (bar + beeswarm kelas smoke), confusion matrix. Registry `airlens-beta-gas` dengan alias sendiri:
production (bawaan) atau challenger (REGISTER_ALIAS=challenger). Tidak mencampuri model AQI maupun model asap.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import mlflow
import mlflow.lightgbm
import numpy as np
import pandas as pd

from airlens.config import load_profile
from airlens.data.beta_gas import CITATION, class_names, feature_names, load_beta_config
from airlens.data.manifest import read_data_version
from airlens.data.paths import processed_dir
from airlens.db.session import get_engine
from airlens.models import registry
from airlens.models.bundle import ARTIFACTS_DIR
from airlens.versioning import code_version, git_commit

logger = logging.getLogger("airlens.train_beta")


def pretty_name(feature: str) -> str:
    """r_mq135 -> MQ-135, mq3_over_mq2 -> MQ-3 / MQ-2 (untuk plot dan kalimat alasan)."""
    if feature == "mq3_over_mq2":
        return "MQ-3 / MQ-2"
    return "MQ-" + feature[len("r_mq"):] if feature.startswith("r_mq") else feature


def metrics(y: np.ndarray, pred: np.ndarray, classes: list[str]) -> dict:
    from sklearn.metrics import confusion_matrix, f1_score, recall_score

    labels = list(range(len(classes)))
    f1 = f1_score(y, pred, labels=labels, average=None, zero_division=0)
    rec = recall_score(y, pred, labels=labels, average=None, zero_division=0)
    return {"n": int(len(y)), "accuracy": float((pred == y).mean()),
            "macro_f1": float(f1.mean()), "f1": {c: float(v) for c, v in zip(classes, f1)},
            "recall": {c: float(v) for c, v in zip(classes, rec)}, "recall_smoke": float(rec[classes.index("smoke")]),
            "confusion_matrix": confusion_matrix(y, pred, labels=labels).tolist()}


def baseline_rule(x: pd.DataFrame, classes: list[str], alert_ratio: float) -> np.ndarray:
    """Aturan Beta lama: hanya MQ-2, rasio di bawah ambang -> smoke, selain itu clean_air."""
    return np.where(x["r_mq2"].to_numpy() < alert_ratio, classes.index("smoke"), classes.index("clean_air"))


def shap_contrib(booster, x: np.ndarray, n_classes: int) -> np.ndarray:
    """TreeSHAP persis dari LightGBM: bentuk (n, kelas, fitur + 1); kolom terakhir = nilai dasar."""
    c = booster.predict(x, pred_contrib=True)
    return np.asarray(c).reshape(len(x), n_classes, -1)


def train(cfg: dict, table: pd.DataFrame, extra: tuple | None = None):
    """extra = (x, y, bobot) tambahan untuk data latih (rekaman alat sendiri, `make import-beta-recordings`)."""
    import lightgbm as lgb

    feats, classes = feature_names(cfg), class_names(cfg)
    split = {s: table[table["split"] == s] for s in ("train", "val", "test")}
    xs = {s: d[feats].to_numpy(dtype=float) for s, d in split.items()}
    ys = {s: np.array([classes.index(v) for v in d["label"]]) for s, d in split.items()}
    m = cfg["model"]
    clf = lgb.LGBMClassifier(objective="multiclass", num_class=len(classes), num_leaves=m["num_leaves"],
                             max_depth=m["max_depth"], learning_rate=m["learning_rate"], n_estimators=m["n_estimators"],
                             min_child_samples=m["min_child_samples"], subsample=m["subsample"],
                             subsample_freq=m["subsample_freq"], colsample_bytree=m["colsample_bytree"],
                             reg_lambda=m["reg_lambda"], random_state=m["seed"], deterministic=True,
                             force_row_wise=True, n_jobs=2, verbose=-1)
    x_fit, y_fit, w_fit = xs["train"], ys["train"], np.ones(len(ys["train"]))
    if extra is not None:
        x_fit, y_fit = np.vstack([x_fit, extra[0]]), np.concatenate([y_fit, extra[1]])
        w_fit = np.concatenate([w_fit, extra[2]])
    clf.fit(x_fit, y_fit, sample_weight=w_fit, eval_X=(xs["val"],), eval_y=(ys["val"],), eval_metric="multi_logloss",
            callbacks=[lgb.early_stopping(m["early_stopping_rounds"], verbose=False)])
    return clf.booster_, xs, ys, split


def plots(booster, x_test: np.ndarray, y_test: np.ndarray, pred: np.ndarray, feats: list[str], classes: list[str],
          out: Path) -> dict:
    """Plot SHAP global (lewat pustaka shap) + pemeriksaan bahwa shap.TreeExplainer = pred_contrib LightGBM."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import shap

    from airlens.models.plots import confusion_matrix_plot

    out.mkdir(parents=True, exist_ok=True)
    explainer = shap.TreeExplainer(booster)
    sv = np.asarray(explainer.shap_values(x_test))              # (n, fitur, kelas) pada shap >= 0.45
    if sv.shape[1] != len(feats):
        sv = np.moveaxis(sv, 0, -1)
    contrib = shap_contrib(booster, x_test, len(classes))       # (n, kelas, fitur + 1)
    max_diff = float(np.abs(np.moveaxis(sv, -1, 1) - contrib[:, :, :-1]).max())

    k = classes.index("smoke")
    pretty = [pretty_name(f) for f in feats]
    plt.figure()
    shap.summary_plot(sv[:, :, k], x_test, feature_names=pretty, show=False, plot_size=(6.5, 3.6))
    plt.title("SHAP for class 'smoke' (test set)")
    plt.tight_layout()
    plt.savefig(out / "shap_beeswarm_smoke.png", dpi=130)
    plt.close("all")

    mean_abs = np.abs(sv).mean(axis=0)                           # (fitur, kelas)
    fig, ax = plt.subplots(figsize=(6.5, 3.6), dpi=130)
    left = np.zeros(len(feats))
    order = np.argsort(mean_abs.sum(1))
    for j, c in enumerate(classes):
        ax.barh(np.array(pretty)[order], mean_abs[order, j], left=left[order], label=c)
        left += mean_abs[:, j]
    ax.set_xlabel("mean |SHAP| (raw score)")
    ax.set_title("Global feature importance per class (test set)")
    ax.legend(fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(out / "shap_bar.png")
    plt.close(fig)
    confusion_matrix_plot(metrics(y_test, pred, classes)["confusion_matrix"], classes, "Beta gas model, test",
                          out / "confusion_test.png")
    return {"shap_vs_pred_contrib_max_abs_diff": max_diff,
            "mean_abs_shap": {f: {c: float(mean_abs[i, j]) for j, c in enumerate(classes)} for i, f in enumerate(feats)}}


def log_and_register(cfg: dict, booster, bundle: Path, meta: dict, log_metrics: dict, alias: str, run_name: str):
    """Catat run MLflow (param, metrik, model, bundle, plot) lalu daftarkan ke registry dengan alias."""
    feats = meta["features"]
    mlflow.set_experiment("airlens-beta-gas")
    with mlflow.start_run(run_name=run_name) as r:
        meta["mlflow_run_id"] = r.info.run_id
        (bundle / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
        mlflow.set_tags({"data_version": meta["data_version"], "profile": meta["profile"],
                         "code_version": code_version(), "git_commit": git_commit() or ""})
        mlflow.log_params({f"param_{k}": v for k, v in cfg["model"].items()} | {"param_features": ",".join(feats)})
        mlflow.log_metrics(log_metrics)
        info = mlflow.lightgbm.log_model(booster, name="model")
        mlflow.log_artifact(str(bundle / "model.txt"), artifact_path="bundle")
        mlflow.log_artifact(str(bundle / "metadata.json"), artifact_path="bundle")
        if (bundle / "plots").exists():
            mlflow.log_artifacts(str(bundle / "plots"), artifact_path="plots")
    name = cfg["registered_model"]
    mv = mlflow.register_model(info.model_uri, name, tags={"data_version": meta["data_version"]})
    engine = get_engine()
    registry.record_registration(engine, mv.version, "candidate", meta, model=name,
                                 metric_keys=("macro_f1", "accuracy", "recall_smoke"))
    (registry.set_challenger if alias == "challenger" else registry.set_production)(engine, mv.version, model=name)
    return mv


def run() -> dict:
    profile = load_profile()["profile"]
    cfg = load_beta_config()
    data_dir = processed_dir(profile) / "beta_gas"
    if not (data_dir / "features.csv").exists():
        raise FileNotFoundError(f"{data_dir}/features.csv belum ada; jalankan `make data-beta PROFILE={profile}`")
    data_version = read_data_version(data_dir)
    table = pd.read_csv(data_dir / "features.csv")
    reference = json.loads((data_dir / "reference.json").read_text())
    feats, classes = feature_names(cfg), class_names(cfg)

    booster, xs, ys, split = train(cfg, table)
    raw = {s: booster.predict(xs[s], raw_score=True) for s in xs}
    pred = {s: raw[s].argmax(1) for s in xs}
    val_m, test_m = metrics(ys["val"], pred["val"], classes), metrics(ys["test"], pred["test"], classes)
    alert = cfg["baseline_rule"]["mq2_alert_ratio"]
    base_m = metrics(ys["test"], baseline_rule(split["test"], classes, alert), classes)
    contrib = shap_contrib(booster, xs["test"], len(classes))
    additivity = float(np.abs(contrib.sum(-1) - raw["test"]).max())
    if additivity > 1e-6:
        raise RuntimeError(f"SHAP tidak aditif (selisih maks {additivity:.2e})")

    bundle = ARTIFACTS_DIR / "models" / "beta_gas" / data_version[:12] / "lightgbm"
    bundle.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(bundle / "model.txt"))
    extra = plots(booster, xs["test"], ys["test"], pred["test"], feats, classes, bundle / "plots")
    meta = {"name": "lightgbm", "kind": "lightgbm", "task": "beta_gas", "classes": classes, "features": feats,
            "sensors": cfg["sensors"], "clean_air_reference_adc": reference,
            "expected_value": contrib[0, :, -1].tolist(), "shap_space": "raw score (softmax log-odds) per class",
            "best_iteration": int(booster.best_iteration or booster.current_iteration()),
            "data_version": data_version, "code_version": code_version(), "git_commit": git_commit(),
            "profile": profile, "params": cfg["model"], "split": cfg["split"], "val_metrics": val_m,
            "test_metrics": test_m, "baseline_rule_test_metrics": base_m, "shap_additivity_max_abs_diff": additivity,
            **extra, "dataset_citation": CITATION, "registered_model": cfg["registered_model"]}

    log_metrics = {"val_macro_f1": val_m["macro_f1"], "test_macro_f1": test_m["macro_f1"],
                   "test_accuracy": test_m["accuracy"], "test_recall_smoke": test_m["recall_smoke"],
                   "baseline_rule_test_macro_f1": base_m["macro_f1"], "best_iteration": meta["best_iteration"],
                   "shap_additivity_max_abs_diff": additivity} | {f"test_f1_{c}": v for c, v in test_m["f1"].items()}
    alias = os.environ.get("REGISTER_ALIAS", "production")
    mv = log_and_register(cfg, booster, bundle, meta, log_metrics, alias, f"beta-gas-lightgbm-{profile}")
    name = cfg["registered_model"]
    result = {"registered_model": name, "version": mv.version, "alias": alias, "val": val_m, "test": test_m,
              "baseline_rule_test": base_m, "shap_additivity_max_abs_diff": additivity,
              "shap_vs_pred_contrib_max_abs_diff": extra["shap_vs_pred_contrib_max_abs_diff"], "bundle": str(bundle)}
    (bundle / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    from airlens.data.paths import RESULTS_DIR

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)   # model gas Beta final untuk arsip (import-results)
    (RESULTS_DIR / "beta_final.json").write_text(json.dumps({"bundle": str(bundle), "version": mv.version,
                                                             "source": "dataset publik", "test": test_m}, indent=2) + "\n")
    logger.info("%s v%s (%s): test macro-F1 %.3f (aturan MQ-2 lama %.3f), recall asap %.3f", name, mv.version, alias,
                test_m["macro_f1"], base_m["macro_f1"], test_m["recall_smoke"])
    return result


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    print(json.dumps(run(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
