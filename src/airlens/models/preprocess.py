"""Preprocessing inferensi yang SAMA untuk evaluasi dan API (numpy + PIL, tanpa PyTorch).

Gambar diubah ukuran utuh ke 224x224 (tanpa center crop): langit di bagian atas adalah petunjuk utama kabut,
jadi tidak boleh terpotong.
"""

import numpy as np
from PIL import Image, ImageOps

IMAGE_SIZE = 224
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)  # ImageNet
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

SPEC = {"resize": [IMAGE_SIZE, IMAGE_SIZE], "interpolation": "bilinear", "mean": MEAN.tolist(), "std": STD.tolist(),
        "layout": "NCHW", "color": "RGB", "exif_transpose": True}


def load_image(path_or_file, size: int = IMAGE_SIZE, draft: bool = False) -> Image.Image:
    """Buka gambar, putar sesuai EXIF, ke RGB.

    draft=True mempercepat decode JPEG (diperkecil saat decode) dan HANYA dipakai saat latih (augmentasi). Validasi,
    evaluasi, referensi monitoring, dan API memakai decode penuh agar masukan model identik dengan saat produksi.
    """
    img = Image.open(path_or_file)
    if draft and img.format == "JPEG":
        img.draft("RGB", (size * 2, size * 2))
    img = ImageOps.exif_transpose(img)
    return img.convert("RGB")


def to_array(img: Image.Image, size: int = IMAGE_SIZE) -> np.ndarray:
    x = np.asarray(img.resize((size, size), Image.BILINEAR), dtype=np.float32) / 255.0
    return ((x - MEAN) / STD).transpose(2, 0, 1)  # CHW


def preprocess(path_or_file, size: int = IMAGE_SIZE) -> np.ndarray:
    return to_array(load_image(path_or_file, size), size)[None]  # 1xCxHxW
