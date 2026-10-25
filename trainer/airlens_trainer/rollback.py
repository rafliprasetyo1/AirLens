"""`make rollback [VERSION=n]`: pindahkan alias production ke versi sebelumnya (atau VERSION) TANPA build ulang.

API memeriksa alias secara berkala dan memuat versi tersebut sendiri (≤ 30 detik).
"""

import os
import sys

from mlflow import MlflowClient

from airlens.db.session import get_engine
from airlens.models import registry


def main() -> int:
    engine = get_engine()
    current = registry.alias_version("production")
    target = os.environ.get("VERSION") or (registry.previous_production(engine, current) if current else None)
    if not target:
        print(f"Tidak ada versi sebelumnya untuk rollback (production sekarang: v{current}). Pakai VERSION=n.")
        return 1
    MlflowClient().get_model_version(registry.REGISTERED_MODEL, str(target))  # gagal jelas bila versi tidak ada
    registry.set_production(engine, target)
    registry.mark_rolled_back(engine, current)
    print(f"Rollback: production v{current} → v{target}. API memuat ulang otomatis dalam ≤ 30 detik.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
