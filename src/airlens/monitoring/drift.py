"""Metrik drift per fitur: PSI (Population Stability Index) dan uji Kolmogorov-Smirnov dua sampel.

PSI dihitung pada bin kuantil data referensi. Jumlah bin mengikuti ukuran sampel sekarang (~10 sampel per bin,
3 sampai 10 bin): PSI bias ke atas pada sampel kecil (10 bin dan 40 sampel: derau acak saja sudah ~0,2).
Patokan umum: < 0,1 stabil, 0,1-0,2 bergeser sedang, > 0,2 bergeser signifikan.

Bias sampel kecil dikoreksi: E[PSI | tanpa drift] ~ (k-1)(1/n + 1/m), dikurangkan dari PSI (psi_adj). Aturan
peringatan (config monitoring.thresholds): psi_adj >= psi_min DAN KS p < ks_p. Diukur pada simulasi 8 fitur
(DECISIONS.md): alarm palsu 4% pada n=60 (PSI mentah > 0,2: 36%), deteksi pergeseran 0,6 sd 94%.
"""

import numpy as np
from scipy.stats import ks_2samp

EPS = 1e-4


def psi(reference: np.ndarray, current: np.ndarray, bins: int | None = None) -> float:
    reference, current = np.asarray(reference, float), np.asarray(current, float)
    bins = bins or int(np.clip(len(current) // 10, 3, 10))
    edges = np.unique(np.quantile(reference, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:  # referensi hampir konstan: PSI tidak bermakna
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf
    ref = np.histogram(reference, edges)[0] / len(reference)
    cur = np.histogram(current, edges)[0] / len(current)
    ref, cur = np.clip(ref, EPS, None), np.clip(cur, EPS, None)
    return float(np.sum((cur - ref) * np.log(cur / ref)))


def ks(reference: np.ndarray, current: np.ndarray) -> tuple[float, float]:
    res = ks_2samp(np.asarray(reference, float), np.asarray(current, float))
    return float(res.statistic), float(res.pvalue)


def drift_table(reference: dict[str, list[float]], current: dict[str, list[float]]) -> dict[str, dict]:
    out = {}
    for name, ref in reference.items():
        cur = [v for v in current.get(name, []) if v is not None and np.isfinite(v)]
        if not cur:
            continue
        stat, p = ks(ref, cur)
        raw = psi(ref, cur)
        k = int(np.clip(len(cur) // 10, 3, 10))
        out[name] = {"psi": round(raw, 4), "psi_adj": round(raw - (k - 1) * (1 / len(cur) + 1 / len(ref)), 4),
                     "ks": round(stat, 4), "ks_p": float(f"{p:.3g}"), "n": len(cur),
                     "ref_median": round(float(np.median(ref)), 4), "cur_median": round(float(np.median(cur)), 4)}
    return out
