"""Unduh dataset dari sumber resmi dengan verifikasi checksum. Bisa dilanjutkan (resume) bila terputus."""

import hashlib
import logging
import os
import time
import zipfile
from pathlib import Path

import requests

from airlens.data.paths import RAW_DIR

logger = logging.getLogger("airlens.data.download")
CHUNK = 1 << 20

# Revisi Hugging Face dipin ke commit; sha256 = oid LFS dari API Hugging Face.
PM25VISION_REVISION = "578bc7c17c99be1aa312ebfe0bda6ce40067ca31"
PM25VISION_FILES = {
    "train.parquet": ("sha256", "e42d2dff2c7ba1ac9736cbe9b6b055e51fffe03dd04c90a368ec13db7dddd3f5"),
    "test.parquet": ("sha256", "76b95649b9dee834ff80d28a0c40cbeb145d283f2885e2476a93f9fe29ad5575"),
}
DHAKA_RECORD = "7878371"
DHAKA_FILES = {  # md5 dari halaman Zenodo
    "dataset.xlsx": ("md5", "392c8f627b92d1a2d893fda364890426"),
    "dataset.rar": ("md5", "47ebcc1e50abc144f56a5a18acbb06de"),
}
INDIA_NEPAL_KAGGLE = "adarshrouniyar/air-pollution-image-dataset-from-india-and-nepal"
INDIA_NEPAL_ZIP = "air-pollution-image-dataset-from-india-and-nepal.zip"


def file_hash(path: Path, algo: str = "sha256") -> str:
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str, dest: Path, algo: str, expected: str, attempts: int = 20) -> Path:
    """Unduh ke dest (resume lewat Range), lalu cocokkan checksum. File yang sudah cocok tidak diunduh ulang.

    Koneksi yang terputus di tengah dilanjutkan dari posisi terakhir, hingga `attempts` kali.
    """
    if dest.exists() and file_hash(dest, algo) == expected:
        logger.info("%s sudah ada dan checksum cocok", dest.name)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(1, attempts + 1):
        try:
            _stream(url, dest, part)
            break
        except requests.exceptions.RequestException as exc:
            logger.warning("%s terputus (%s), lanjut dari %d MB, percobaan %d/%d",
                           dest.name, type(exc).__name__, part.stat().st_size // 2**20 if part.exists() else 0,
                           attempt, attempts)
            time.sleep(min(60, 5 * attempt))
    else:
        raise RuntimeError(f"{dest.name}: gagal setelah {attempts} percobaan; jalankan ulang untuk melanjutkan")
    got = file_hash(part, algo)
    if got != expected:
        part.unlink()
        raise RuntimeError(f"checksum {dest.name} tidak cocok: {algo} {got} != {expected}")
    part.rename(dest)
    logger.info("%s selesai, %s cocok", dest.name, algo)
    return dest


def _stream(url: str, dest: Path, part: Path) -> None:
    start = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={start}-"} if start else {}
    with requests.get(url, headers=headers, stream=True, timeout=60) as r:
        if start and r.status_code == 416:  # sudah lengkap
            return
        r.raise_for_status()
        if start and r.status_code != 206:
            start = 0  # server mengabaikan Range dan mengirim dari awal: tulis ulang, jangan disambung
        total = int(r.headers.get("Content-Length", 0)) + start
        with open(part, "ab" if start else "wb") as f:
            done = start
            for i, chunk in enumerate(r.iter_content(CHUNK)):
                f.write(chunk)
                done += len(chunk)
                if i % 100 == 0:
                    logger.info("%s: %.0f/%.0f MB", dest.name, done / 2**20, total / 2**20)


def download_pm25vision() -> Path:
    out = RAW_DIR / "pm25vision"
    for name, (algo, digest) in PM25VISION_FILES.items():
        url = f"https://huggingface.co/datasets/DeadCardassian/PM25Vision/resolve/{PM25VISION_REVISION}/{name}"
        fetch(url, out / name, algo, digest)
    return out


def download_dhaka() -> Path:
    out = RAW_DIR / "dhaka"
    for name, (algo, digest) in DHAKA_FILES.items():
        fetch(f"https://zenodo.org/records/{DHAKA_RECORD}/files/{name}?download=1", out / name, algo, digest)
    return out


def download_india_nepal() -> Path:
    """Kaggle tidak menyediakan checksum; sha256 arsip dicatat di CHECKSUMS.txt untuk dibandingkan antar mesin.

    Zip boleh diletakkan manual (unduh dari browser) dengan nama yang sama; API Kaggle hanya dipanggil bila belum ada.
    """
    out = RAW_DIR / "india_nepal"
    out.mkdir(parents=True, exist_ok=True)
    archive = out / INDIA_NEPAL_ZIP
    if not archive.exists():
        if not (os.environ.get("KAGGLE_USERNAME") and os.environ.get("KAGGLE_KEY")):
            raise RuntimeError(f"{archive} belum ada dan KAGGLE_USERNAME/KAGGLE_KEY kosong di .env")
        from kaggle.api.kaggle_api_extended import KaggleApi  # impor di sini: modul kaggle langsung butuh kredensial

        api = KaggleApi()
        api.authenticate()
        api.dataset_download_files(INDIA_NEPAL_KAGGLE, path=str(out), unzip=False, quiet=False)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise RuntimeError(f"{archive.name} rusak (CRC tidak cocok)")
    digest = file_hash(archive)
    checksum_file = out / "CHECKSUMS.txt"
    if checksum_file.exists() and digest not in checksum_file.read_text():
        raise RuntimeError(f"arsip India-Nepal berbeda dari unduhan sebelumnya (sha256 {digest})")
    checksum_file.write_text(f"{digest}  {archive.name}\n")
    return archive
