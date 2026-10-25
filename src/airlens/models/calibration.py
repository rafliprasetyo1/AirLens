"""Temperature scaling (Guo et al., 2017) dan pemilihan ambang "belum pasti". Keduanya HANYA disetel di validasi."""

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import log_softmax, softmax


def nll(logits: np.ndarray, y: np.ndarray, temperature: float) -> float:
    return float(-log_softmax(logits / temperature, axis=1)[np.arange(len(y)), y].mean())


def fit_temperature(logits: np.ndarray, y: np.ndarray) -> float:
    """T > 0 yang meminimalkan NLL; dicari pada log T agar positif dan stabil."""
    res = minimize_scalar(lambda log_t: nll(logits, y, float(np.exp(log_t))), bounds=(np.log(0.05), np.log(20.0)),
                          method="bounded", options={"xatol": 1e-4})
    return float(np.exp(res.x))


def calibrated_probs(logits: np.ndarray, temperature: float) -> np.ndarray:
    return softmax(logits / temperature, axis=1)


def choose_threshold(probs: np.ndarray, y: np.ndarray, target_accuracy: float, min_accepted: int) -> dict:
    """Ambang terkecil (cakupan terbesar) yang membuat akurasi prediksi yang diterima >= target.

    Bila target tidak tercapai dengan minimal `min_accepted` prediksi diterima, kembalikan ambang dengan akurasi
    tertinggi di antara pilihan yang menerima >= min_accepted, dan tandai target_tercapai=False (dilaporkan, tidak
    disembunyikan).
    """
    conf = probs.max(axis=1)
    correct = (probs.argmax(axis=1) == y).astype(float)
    order = np.argsort(-conf, kind="stable")
    cum_acc = np.cumsum(correct[order]) / np.arange(1, len(order) + 1)
    sorted_conf = conf[order]
    # Ambang hanya boleh di batas antar nilai keyakinan berbeda (semua seri ikut diterima).
    last_of_tie = np.r_[sorted_conf[1:] != sorted_conf[:-1], True]
    valid = last_of_tie & (np.arange(1, len(order) + 1) >= min_accepted)
    if not valid.any():
        return {"threshold": 0.0, "target_tercapai": False, "val_coverage": 1.0, "val_accepted_accuracy": float(correct.mean())}
    ok = valid & (cum_acc >= target_accuracy)
    reached = bool(ok.any())
    k = int(np.flatnonzero(ok).max()) if reached else int(np.flatnonzero(valid)[np.argmax(cum_acc[valid])])
    return {
        "threshold": float(sorted_conf[k]),
        "target_tercapai": reached,
        "val_coverage": float((k + 1) / len(order)),
        "val_accepted_accuracy": float(cum_acc[k]),
    }
