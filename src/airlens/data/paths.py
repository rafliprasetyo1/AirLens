import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("AIRLENS_DATA_DIR", "/app/data"))
RESULTS_DIR = Path(os.environ.get("AIRLENS_RESULTS_DIR", "/app/results"))
RAW_DIR = DATA_DIR / "raw"
IMAGES_DIR = DATA_DIR / "images"
INTERIM_DIR = DATA_DIR / "interim"


def processed_dir(profile: str) -> Path:
    return DATA_DIR / "processed" / profile
