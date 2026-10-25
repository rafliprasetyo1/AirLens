"""Versi kode untuk pelacakan run. Selama repo belum punya commit, code_version (hash isi kode) yang dipakai."""

import hashlib
import os
from pathlib import Path

CODE_DIRS = ("src", "trainer", "config", "requirements")


def code_version(root: Path = Path("/app")) -> str:
    h = hashlib.sha256()
    for d in CODE_DIRS:
        for f in sorted((root / d).rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                h.update(str(f.relative_to(root)).encode())
                h.update(f.read_bytes())
    return h.hexdigest()


def git_commit() -> str:
    return os.environ.get("GIT_COMMIT", "belum-ada-commit")


def is_smoke() -> bool:
    """Uji asap (`make train SMOKE=1`): alur dijalankan sangat singkat; hasilnya bukan hasil evaluasi."""
    return os.environ.get("AIRLENS_SMOKE", "0") == "1"


def apply_smoke(training: dict) -> dict:
    if not is_smoke():
        return training
    return {**training, "models": training["models"][:1], "epochs_head": 1, "epochs_full": 0, "patience": 1}
