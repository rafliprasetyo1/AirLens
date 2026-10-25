"""Validasi unggahan: ukuran, tipe ASLI (isi file, bukan ekstensi), batas piksel, dan penghapusan metadata.

EXIF (termasuk GPS) dibuang dengan menyalin piksel ke gambar baru. Orientasi EXIF diterapkan lebih dulu agar foto tidak
terbalik; tag GPS tidak pernah dibaca.
"""

import io

from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
MAX_PIXELS = 40_000_000  # ~40 MP; lebih dari ini ditolak (perlindungan decompression bomb)


class UploadRejected(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def validate_and_strip(data: bytes, max_bytes: int) -> tuple[Image.Image, str]:
    """Kembalikan (gambar RGB tanpa metadata, format asli) atau lempar UploadRejected."""
    if not data:
        raise UploadRejected("file_kosong", "File kosong.")
    if len(data) > max_bytes:
        raise UploadRejected("terlalu_besar", f"Ukuran file melebihi {max_bytes // 2**20} MB.")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            width, height = probe.size
            probe.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise UploadRejected("bukan_gambar", "File bukan gambar yang valid atau rusak.") from None
    if fmt not in ALLOWED_FORMATS:
        raise UploadRejected("tipe_tidak_didukung", "Format harus JPEG, PNG, atau WebP.")
    if width * height > MAX_PIXELS:
        raise UploadRejected("terlalu_besar", "Resolusi gambar terlalu besar.")
    try:
        with Image.open(io.BytesIO(data)) as img:
            rgb = ImageOps.exif_transpose(img).convert("RGB")
    except (OSError, ValueError, Image.DecompressionBombError):
        raise UploadRejected("bukan_gambar", "Gambar tidak bisa dibaca.") from None
    clean = Image.new("RGB", rgb.size)
    clean.paste(rgb)  # salin piksel saja: tidak membawa EXIF/ICC/XMP
    return clean, fmt
