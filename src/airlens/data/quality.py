"""Filter kualitas gambar: rusak, terlalu kecil, gelap/malam, terlalu terang, langit tidak terlihat.

Heuristik "langit terlihat": porsi piksel mirip-langit (terang dan halus secara lokal) di 40% atas gambar.
Versi pertama (tekstur rata-rata sepertiga atas) ditolak setelah cek visual: ranting dan gedung berlatar langit
membuat hampir semua foto jalan dianggap tanpa langit. Sampel yang ditolak tetap disimpan sebagai grid.
"""

from dataclasses import asdict, dataclass

import numpy as np
from PIL import Image, ImageOps

# Ambang awal; disetel dengan melihat grid sampel, dicatat di DATA_CARD.md.
MIN_SIDE = 100
DARK_MEAN = 45  # luminance rata-rata 0-255
BRIGHT_MEAN = 235
SATURATED_FRAC = 0.5  # porsi piksel >= 250
SKY_LUM_MIN = 90  # piksel langit: cukup terang...
SKY_GRAD_MAX = 6.0  # ...dan halus (gradien lokal kecil)
SKY_TOP = 0.4  # bagian atas gambar yang diperiksa
SKY_MIN_FRAC = 0.05  # disetel dari grid kalibrasi, lihat DATA_CARD.md
NIGHT_HOURS = set(range(0, 6)) | set(range(19, 24))  # jam lokal; hanya bila jam diketahui


@dataclass
class ImageStats:
    width: int
    height: int
    mean_lum: float
    std_lum: float
    mean_sat: float
    frac_saturated: float
    sky_frac: float


def load_rgb(path) -> Image.Image:
    img = Image.open(path)
    img.load()
    return ImageOps.exif_transpose(img).convert("RGB")


def image_stats(img: Image.Image) -> ImageStats:
    small = img.copy()
    small.thumbnail((256, 256))
    rgb = np.asarray(small, dtype=np.float32)
    lum = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    gy = np.abs(np.diff(lum, axis=0, prepend=lum[:1]))
    gx = np.abs(np.diff(lum, axis=1, prepend=lum[:, :1]))
    top = slice(0, max(1, int(lum.shape[0] * SKY_TOP)))
    sky = (lum[top] >= SKY_LUM_MIN) & (np.maximum(gx[top], gy[top]) <= SKY_GRAD_MAX)
    return ImageStats(
        width=img.width,
        height=img.height,
        mean_lum=float(lum.mean()),
        std_lum=float(lum.std()),
        mean_sat=float(sat.mean()),
        frac_saturated=float((lum >= 250).mean()),
        sky_frac=float(sky.mean()),
    )


def reject_reason(stats: ImageStats | None, hour: int | None = None) -> str | None:
    """Alasan penolakan pertama yang cocok, atau None bila lolos. Urutan menentukan pelaporan."""
    if stats is None:
        return "rusak"
    if min(stats.width, stats.height) < MIN_SIDE:
        return "terlalu_kecil"
    if hour is not None and hour in NIGHT_HOURS:
        return "malam"
    if stats.mean_lum < DARK_MEAN:
        return "terlalu_gelap"
    if stats.mean_lum > BRIGHT_MEAN or stats.frac_saturated > SATURATED_FRAC:
        return "terlalu_terang"
    if stats.sky_frac < SKY_MIN_FRAC:
        return "langit_tidak_terlihat"
    return None


def assess(path, hour: int | None = None) -> dict:
    try:
        stats = image_stats(load_rgb(path))
    except Exception:  # file rusak/terpotong/bukan gambar: semua dianggap rusak
        stats = None
    out = asdict(stats) if stats else {}
    out["reject_reason"] = reject_reason(stats, hour)
    return out
