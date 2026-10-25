"""Fitur kabut klasik untuk baseline.

- Dark channel prior (He et al., 2009): di udara bersih, patch luar ruangan punya kanal warna yang gelap;
  kabut menaikkan dark channel dan menurunkan transmisi.
- Kontras (RMS dan Michelson), saturasi, kecerahan, entropi histogram, ketajaman (variansi Laplacian),
  dan warna langit (bagian atas gambar).
Semua dihitung pada gambar yang diperkecil (sisi terpanjang 256 px) agar cepat dan tidak bergantung resolusi asli.
"""

import numpy as np
from PIL import Image
from scipy import ndimage

SIDE = 256
DCP_PATCH = 15
DCP_OMEGA = 0.95

FEATURE_NAMES = (
    "dark_mean", "dark_median", "dark_p90", "transmission_mean", "transmission_top",
    "atmo_light", "contrast_rms", "contrast_michelson", "sat_mean", "sat_std",
    "lum_mean", "lum_p05", "lum_p95", "entropy", "sharpness",
    "sky_r", "sky_g", "sky_b", "sky_blue_ratio", "sky_sat",
)


def _prepare(img: Image.Image) -> np.ndarray:
    small = img.convert("RGB").copy()
    small.thumbnail((SIDE, SIDE))
    return np.asarray(small, dtype=np.float32) / 255.0


def dark_channel(rgb: np.ndarray, patch: int = DCP_PATCH) -> np.ndarray:
    return ndimage.minimum_filter(rgb.min(axis=2), size=patch, mode="nearest")


def haze_features(img: Image.Image) -> dict[str, float]:
    rgb = _prepare(img)
    lum = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    dark = dark_channel(rgb)

    # Cahaya atmosfer: rata-rata piksel asli pada 0,1% dark channel tertinggi.
    n_top = max(1, dark.size // 1000)
    idx = np.argpartition(dark.ravel(), -n_top)[-n_top:]
    atmo = rgb.reshape(-1, 3)[idx].mean(axis=0).clip(1e-3, 1.0)
    transmission = 1.0 - DCP_OMEGA * dark_channel(rgb / atmo)

    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    p01, p99 = np.percentile(lum, [1, 99])
    hist, _ = np.histogram(lum, bins=256, range=(0.0, 1.0))
    prob = hist[hist > 0] / hist.sum()
    laplace = ndimage.laplace(lum)

    top = slice(0, max(1, lum.shape[0] // 5))
    sky = rgb[top].reshape(-1, 3).mean(axis=0)
    return {
        "dark_mean": float(dark.mean()),
        "dark_median": float(np.median(dark)),
        "dark_p90": float(np.percentile(dark, 90)),
        "transmission_mean": float(transmission.mean()),
        "transmission_top": float(transmission[top].mean()),
        "atmo_light": float(atmo.mean()),
        "contrast_rms": float(lum.std()),
        "contrast_michelson": float((p99 - p01) / (p99 + p01 + 1e-6)),
        "sat_mean": float(sat.mean()),
        "sat_std": float(sat.std()),
        "lum_mean": float(lum.mean()),
        "lum_p05": float(np.percentile(lum, 5)),
        "lum_p95": float(np.percentile(lum, 95)),
        "entropy": float(-(prob * np.log2(prob)).sum()),
        "sharpness": float(laplace.var()),
        "sky_r": float(sky[0]),
        "sky_g": float(sky[1]),
        "sky_b": float(sky[2]),
        "sky_blue_ratio": float(sky[2] / (sky.sum() + 1e-6)),
        "sky_sat": float(sat[top].mean()),
    }


# Petunjuk visual yang ditampilkan ke pengguna. "naik" = nilai lebih tinggi berarti lebih berkabut.
HINTS = {
    "contrast_rms": {"label": "Kontras", "hazier": "turun"},
    "dark_mean": {"label": "Dark channel (lapisan kabut)", "hazier": "naik"},
    "sky_lum": {"label": "Kecerahan langit", "hazier": "naik"},
}


def hint_values(feats) -> dict[str, float]:
    """Nilai petunjuk dari dict/Series fitur (fungsi yang sama dipakai trainer dan API)."""
    return {
        "contrast_rms": float(feats["contrast_rms"]),
        "dark_mean": float(feats["dark_mean"]),
        "sky_lum": float(0.299 * feats["sky_r"] + 0.587 * feats["sky_g"] + 0.114 * feats["sky_b"]),
    }
