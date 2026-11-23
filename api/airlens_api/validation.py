"""Validasi unggahan: ukuran, tipe ASLI (isi file, bukan ekstensi), batas piksel, dan penghapusan metadata.

EXIF (termasuk GPS) dibuang dengan menyalin piksel ke gambar baru. Orientasi EXIF diterapkan lebih dulu agar foto tidak
terbalik; tag GPS tidak pernah dibaca.
"""

import io

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

register_heif_opener()  # foto HEIF/HEIC (bawaan iPhone) dibuka Pillow seperti format lain; EXIF tetap dibuang di bawah

# JPEG mencakup berkas .jpg dan .jpeg (format yang sama); HEIF mencakup .heic dan .heif.
# MPO = JPEG berisi beberapa gambar (iPhone menyisipkan peta kedalaman/HDR saat mengonversi HEIC ke JPEG ketika
# diunggah). Pillow memakai gambar utamanya; gambar tambahan ikut terbuang bersama metadata.
ALLOWED_FORMATS = {"JPEG": "image/jpeg", "MPO": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp", "HEIF": "image/heif"}
MAX_PIXELS = 40_000_000  # ~40 MP; lebih dari ini ditolak (perlindungan decompression bomb)


class UploadRejected(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def validate_and_strip(data: bytes, max_bytes: int) -> tuple[Image.Image, str]:
    """Kembalikan (gambar RGB tanpa metadata, format asli) atau lempar UploadRejected."""
    if not data:
        raise UploadRejected("file_kosong", "The file is empty.")
    if len(data) > max_bytes:
        raise UploadRejected("terlalu_besar", f"The file is larger than {max_bytes // 2**20} MB.")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            width, height = probe.size
            probe.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise UploadRejected("bukan_gambar", "The file is not a valid image or is damaged.") from None
    if fmt not in ALLOWED_FORMATS:
        raise UploadRejected("tipe_tidak_didukung", f"Use a JPG/JPEG, PNG, WebP or HEIF/HEIC photo (detected: {fmt}).")
    if width * height > MAX_PIXELS:
        raise UploadRejected("terlalu_besar", "The image resolution is too large.")
    try:
        with Image.open(io.BytesIO(data)) as img:
            rgb = ImageOps.exif_transpose(img).convert("RGB")
    except (OSError, ValueError, Image.DecompressionBombError):
        raise UploadRejected("bukan_gambar", "The image could not be read.") from None
    clean = Image.new("RGB", rgb.size)
    clean.paste(rgb)  # salin piksel saja: tidak membawa EXIF/ICC/XMP
    return clean, fmt
