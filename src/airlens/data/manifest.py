"""Manifest data: satu baris per gambar terpakai + sha256-nya. data_version = sha256 isi manifest."""

import hashlib
from pathlib import Path

import pandas as pd

MANIFEST_COLUMNS = ["image_path", "sha256", "split", "label", "source", "location_id", "split_group"]


def write_manifest(df: pd.DataFrame, out_dir: Path) -> str:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = df[MANIFEST_COLUMNS].sort_values("image_path").reset_index(drop=True)
    path = out_dir / "manifest.csv"
    manifest.to_csv(path, index=False, lineterminator="\n")
    version = hashlib.sha256(path.read_bytes()).hexdigest()
    (out_dir / "data_version.txt").write_text(version + "\n")
    return version


def read_data_version(out_dir: Path) -> str:
    return (out_dir / "data_version.txt").read_text().strip()
