"""Konfigurasi bersama: profil YAML dipilih lewat APP_PROFILE, rahasia dari environment."""

import os
from pathlib import Path
from urllib.parse import quote_plus

import yaml

PROFILES = ("laptop", "lab")
CONFIG_DIR = Path(os.environ.get("AIRLENS_CONFIG_DIR", Path(__file__).resolve().parents[2] / "config"))


def load_profile(name: str | None = None) -> dict:
    name = name or os.environ.get("APP_PROFILE", "laptop")
    if name not in PROFILES:
        raise ValueError(f"APP_PROFILE harus salah satu dari {PROFILES}, bukan {name!r}")
    with open(CONFIG_DIR / f"{name}.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if cfg.get("profile") != name:
        raise ValueError(f"config/{name}.yaml berisi profile={cfg.get('profile')!r}")
    return cfg


def database_url() -> str:
    """URL SQLAlchemy dari variabel POSTGRES_*; kredensial di-escape agar aman di URL."""
    user = quote_plus(os.environ["POSTGRES_USER"])
    password = quote_plus(os.environ["POSTGRES_PASSWORD"])
    host = os.environ.get("POSTGRES_HOST", "db")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "airlens")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"
