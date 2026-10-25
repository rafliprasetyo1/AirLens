"""Metrik evaluasi: klasifikasi, kalibrasi (ECE), dan prediksi selektif (ambang "belum pasti")."""

import numpy as np
from sklearn.metrics import balanced_accuracy_score, confusion_matrix, f1_score, recall_score


def classification_metrics(y_true: np.ndarray, y_pred: np.ndarray, n_classes: int) -> dict:
    labels = list(range(n_classes))
    recalls = recall_score(y_true, y_pred, labels=labels, average=None, zero_division=0)
    return {
        "accuracy": float((y_true == y_pred).mean()) if len(y_true) else float("nan"),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)) if len(y_true) else float("nan"),
        "macro_f1": float(f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)),
        "recall_per_class": [float(r) for r in recalls],
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist(),
    }


def reliability_bins(probs: np.ndarray, y_true: np.ndarray, n_bins: int = 15) -> list[dict]:
    """Bin keyakinan (probabilitas maksimum) dengan lebar sama; per bin: rata-rata keyakinan, akurasi, jumlah."""
    conf = probs.max(axis=1)
    correct = probs.argmax(axis=1) == y_true
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (conf > lo) & (conf <= hi) if lo > 0 else (conf >= lo) & (conf <= hi)
        n = int(mask.sum())
        out.append({"lo": float(lo), "hi": float(hi), "n": n,
                    "confidence": float(conf[mask].mean()) if n else float("nan"),
                    "accuracy": float(correct[mask].mean()) if n else float("nan")})
    return out


def expected_calibration_error(probs: np.ndarray, y_true: np.ndarray, n_bins: int = 15) -> float:
    bins = reliability_bins(probs, y_true, n_bins)
    total = len(y_true)
    return float(sum(b["n"] / total * abs(b["accuracy"] - b["confidence"]) for b in bins if b["n"]))


def selective_metrics(probs: np.ndarray, y_true: np.ndarray, threshold: float, n_classes: int) -> dict:
    """Prediksi dengan keyakinan < ambang berstatus "belum pasti" (ditolak)."""
    conf = probs.max(axis=1)
    accepted = conf >= threshold
    y_pred = probs.argmax(axis=1)
    acc = classification_metrics(y_true[accepted], y_pred[accepted], n_classes) if accepted.any() else None
    return {
        "threshold": float(threshold),
        "rejected_fraction": float(1.0 - accepted.mean()),
        "n_accepted": int(accepted.sum()),
        "accepted_accuracy": acc["accuracy"] if acc else float("nan"),
        "accepted_balanced_accuracy": acc["balanced_accuracy"] if acc else float("nan"),
    }


def risk_coverage(probs: np.ndarray, y_true: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Untuk tiap ambang (keyakinan terurut menurun): cakupan, akurasi prediksi yang diterima, ambang."""
    conf = probs.max(axis=1)
    correct = (probs.argmax(axis=1) == y_true).astype(float)
    order = np.argsort(-conf, kind="stable")
    n = np.arange(1, len(order) + 1)
    return n / len(order), np.cumsum(correct[order]) / n, conf[order]
