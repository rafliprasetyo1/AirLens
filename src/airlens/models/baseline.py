"""Baseline: kelas mayoritas (batas bawah), logistic regression, dan GBM pada fitur kabut klasik.

Fitur dihitung sekali per data_version dan disimpan di artifacts/features/. Hyperparameter dipilih dengan grid kecil
berdasarkan macro-F1 di VALIDASI (test tidak disentuh).
"""

import logging
from concurrent.futures import ProcessPoolExecutor
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from airlens.features.haze import FEATURE_NAMES, haze_features
from airlens.models.preprocess import load_image

logger = logging.getLogger("airlens.models.baseline")


def _features_one(path: str) -> list[float]:
    feats = haze_features(load_image(path, size=256, draft=True))  # baseline tidak di-deploy; draft demi kecepatan
    return [feats[n] for n in FEATURE_NAMES]


def feature_table(paths: list[str], rel_paths: list[str], cache: Path, workers: int) -> pd.DataFrame:
    """Fitur per image_path (relatif). Cache parquet per data_version; hanya gambar yang belum ada yang dihitung."""
    cached = pd.read_parquet(cache) if cache.exists() else pd.DataFrame(columns=["image_path", *FEATURE_NAMES])
    todo = [(p, r) for p, r in zip(paths, rel_paths) if r not in set(cached["image_path"])]
    if todo:
        logger.info("hitung fitur kabut untuk %d gambar", len(todo))
        with ProcessPoolExecutor(max_workers=workers) as pool:
            rows = list(pool.map(_features_one, [p for p, _ in todo], chunksize=16))
        new = pd.DataFrame(rows, columns=list(FEATURE_NAMES))
        new.insert(0, "image_path", [r for _, r in todo])
        cached = pd.concat([cached, new], ignore_index=True)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cached.to_parquet(cache, index=False)
    return cached.set_index("image_path").loc[rel_paths, list(FEATURE_NAMES)]


def _macro_f1(model, x: np.ndarray, y: np.ndarray, n_classes: int) -> float:
    return f1_score(y, model.predict(x), labels=list(range(n_classes)), average="macro", zero_division=0)


def fit_baselines(x_tr, y_tr, x_val, y_val, n_classes: int, seed: int) -> dict[str, dict]:
    """Kembalikan {nama: {"model", "params", "val_macro_f1"}} dengan hyperparameter terbaik di validasi."""
    out = {"majority": {"model": DummyClassifier(strategy="most_frequent").fit(x_tr, y_tr), "params": {}}}

    best = None
    for c in (0.01, 0.1, 1.0, 10.0):
        m = make_pipeline(StandardScaler(), LogisticRegression(C=c, class_weight="balanced", max_iter=5000,
                                                               random_state=seed)).fit(x_tr, y_tr)
        score = _macro_f1(m, x_val, y_val, n_classes)
        if best is None or score > best[0]:
            best = (score, m, {"C": c})
    out["logreg"] = {"model": best[1], "params": best[2]}

    best = None
    for lr, depth, leaf in product((0.05, 0.1), (3, None), (10, 30)):
        m = HistGradientBoostingClassifier(learning_rate=lr, max_depth=depth, min_samples_leaf=leaf, max_iter=300,
                                           class_weight="balanced", early_stopping=False, random_state=seed)
        m.fit(x_tr, y_tr)
        score = _macro_f1(m, x_val, y_val, n_classes)
        if best is None or score > best[0]:
            best = (score, m, {"learning_rate": lr, "max_depth": depth, "min_samples_leaf": leaf})
    out["gbm"] = {"model": best[1], "params": best[2]}

    for name, info in out.items():
        info["val_macro_f1"] = _macro_f1(info["model"], x_val, y_val, n_classes)
    return out


def logits_from_proba(model, x: np.ndarray, n_classes: int) -> np.ndarray:
    """Log-probabilitas sebagai "logit" agar temperature scaling berlaku seragam untuk semua model.

    Kelas yang tidak pernah dilihat model (tidak ada di train) diberi probabilitas sangat kecil.
    """
    proba = np.full((len(x), n_classes), 1e-6)
    proba[:, model.classes_] = model.predict_proba(x)
    proba /= proba.sum(axis=1, keepdims=True)
    return np.log(np.clip(proba, 1e-9, 1.0))
