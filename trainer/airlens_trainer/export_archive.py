"""Arsip hasil tanpa Docker (Kaggle Notebook): format sama dengan scripts/export_results.sh.

    python -m airlens_trainer.export_archive --profile kaggle --logs <dir> --mlflow-dir <dir> --out <dir>

Isi folder airlens_results_<profil>_<waktu>/: results/ (tanpa arsip lama/fixture UI), artifacts/models (bundle ONNX +
metadata), logs/, data_summary/, mlflow.tar.gz (MLflow SQLite + artefak; pengganti mlflow_db.sql +
mlartifacts.tar.gz di lab), ENVIRONMENT.txt, MANIFEST.sha256. Nilai rahasia dari environment (KAGGLE_KEY, dll.)
diperiksa tidak ikut; bila ada, arsip dibatalkan. `make import-results` membaca arsip ini sama seperti arsip lab.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

from airlens.data.paths import DATA_DIR, RESULTS_DIR, processed_dir
from airlens.models.bundle import ARTIFACTS_DIR

SECRET_KEYS = ("POSTGRES_PASSWORD", "IQAIR_API_KEY", "KAGGLE_KEY", "MAPILLARY_ACCESS_TOKEN", "OPENAQ_API_KEY",
               "VAPID_PRIVATE_KEY", "SENSOR_TOKEN", "NODE_TOKEN", "ADMIN_TOKEN", "NGROK_AUTHTOKEN")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def contains_secret(root: Path) -> str | None:
    secrets = {k: os.environ.get(k, "") for k in SECRET_KEYS}
    secrets = {k: v.encode() for k, v in secrets.items() if len(v) >= 8}
    if not secrets:
        return None
    for p in root.rglob("*"):
        if p.is_file() and p.stat().st_size < 200 * 2**20:
            data = p.read_bytes()
            for k, v in secrets.items():
                if v in data:
                    return f"{k} di {p.relative_to(root)}"
    return None


def build(profile: str, logs: Path | None, mlflow_dir: Path | None, out_dir: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"airlens_results_{profile}_{ts}"
    stage = Path(tempfile.mkdtemp())
    out = stage / name
    out.mkdir()
    try:
        if RESULTS_DIR.exists():
            shutil.copytree(RESULTS_DIR, out / "results",
                            ignore=shutil.ignore_patterns("airlens_results_*", "ui", "imported"))
        if (ARTIFACTS_DIR / "models").exists():
            shutil.copytree(ARTIFACTS_DIR / "models", out / "artifacts" / "models", ignore=shutil.ignore_patterns("*.tmp"))
        if logs and logs.exists():
            shutil.copytree(logs, out / "logs")
        proc = processed_dir(profile)
        if proc.exists():
            (out / "data_summary").mkdir()
            for f in ("report.json", "manifest.csv", "data_version.txt"):
                if (proc / f).exists():
                    shutil.copy2(proc / f, out / "data_summary" / f)
        if mlflow_dir and mlflow_dir.exists():
            with tarfile.open(out / "mlflow.tar.gz", "w:gz") as t:
                t.add(mlflow_dir, arcname="mlflow")
        dv = (proc / "data_version.txt").read_text().strip() if (proc / "data_version.txt").exists() else "-"
        gpu = "-"
        try:
            import torch

            gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "tidak ada"
        except Exception:
            pass
        (out / "ENVIRONMENT.txt").write_text(
            f"profil: {profile}\nwaktu: {datetime.now().isoformat(timespec='seconds')}\n"
            f"git: {os.environ.get('GIT_COMMIT', '-')}\npython: {platform.python_version()}\ngpu: {gpu}\n"
            f"data_version: {dv}\nmlflow: sqlite (mlflow.tar.gz)\n")
        leak = contains_secret(out)
        if leak:
            raise SystemExit(f"BATAL: nilai rahasia ditemukan di arsip ({leak})")
        for p in out.rglob(".env"):
            p.unlink()
        lines = [f"{sha256(p)}  ./{p.relative_to(out)}" for p in sorted(out.rglob("*"))
                 if p.is_file() and p.name != "MANIFEST.sha256"]
        (out / "MANIFEST.sha256").write_text("\n".join(lines) + "\n")
        out_dir.mkdir(parents=True, exist_ok=True)
        archive = out_dir / f"{name}.tar.gz"
        with tarfile.open(archive, "w:gz") as t:
            t.add(out, arcname=name)
        return archive
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=os.environ.get("APP_PROFILE", "kaggle"))
    ap.add_argument("--logs", type=Path)
    ap.add_argument("--mlflow-dir", type=Path)
    ap.add_argument("--out", type=Path, default=RESULTS_DIR)
    a = ap.parse_args()
    archive = build(a.profile, a.logs, a.mlflow_dir, a.out)
    print(f"Selesai: {archive} ({archive.stat().st_size / 2**20:.0f} MB)")
    print(json.dumps({"archive": str(archive)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
