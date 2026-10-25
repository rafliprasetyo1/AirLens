"""Tanda tangan input satu gambar: fitur yang dipantau untuk drift.

SATU fungsi dipakai trainer (referensi dari data latih) dan API (tiap prediksi) dengan jalur kode yang sama, sehingga
perbedaan cara decode tidak terbaca sebagai drift palsu.
"""

import numpy as np
from PIL import Image

from airlens.data.quality import image_stats
from airlens.features.haze import haze_features, hint_values

FEATURES = ("mean_lum", "std_lum", "mean_sat", "sky_frac", "contrast_rms", "dark_mean", "sky_lum")
FEATURE_LABELS = {
    "mean_lum": "kecerahan", "std_lum": "kontras luminance", "mean_sat": "saturasi", "sky_frac": "porsi langit",
    "contrast_rms": "kontras RMS", "dark_mean": "dark channel", "sky_lum": "kecerahan langit",
}
N_PCA = 8


def input_signature(img: Image.Image) -> dict[str, float]:
    st = image_stats(img)
    hints = hint_values(haze_features(img))
    return {"mean_lum": st.mean_lum, "std_lum": st.std_lum, "mean_sat": st.mean_sat, "sky_frac": st.sky_frac, **hints}


def fit_pca(emb: np.ndarray, k: int = N_PCA) -> dict:
    """PCA embedding data latih (SVD). Disimpan di metadata model untuk memproyeksikan embedding produksi."""
    mean = emb.mean(axis=0)
    _, s, vt = np.linalg.svd(emb - mean, full_matrices=False)
    k = min(k, vt.shape[0])
    var = s**2
    return {"mean": mean.round(6).tolist(), "components": vt[:k].round(6).tolist(),
            "explained": (var[:k] / var.sum()).round(4).tolist()}


def project(emb: np.ndarray, pca: dict) -> np.ndarray:
    return (np.atleast_2d(emb) - np.asarray(pca["mean"])) @ np.asarray(pca["components"]).T
