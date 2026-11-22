"""`make rollback [VERSION=n]` / `make rollback-smoke`: pindahkan alias production ke versi sebelumnya (atau VERSION)
TANPA build ulang. MODEL=airlens-beta-gas memilih model gas Beta; default model AQI (perilaku lama).

API memeriksa alias secara berkala dan memuat versi tersebut sendiri (≤ 30 detik).
"""

import os
import sys

from mlflow import MlflowClient

from airlens.db.session import get_engine
from airlens.models import registry


def main() -> int:
    engine = get_engine()
    model = os.environ.get("MODEL") or registry.REGISTERED_MODEL
    current = registry.alias_version("production", model=model)
    target = os.environ.get("VERSION") or (registry.previous_production(engine, current, model) if current else None)
    if not target:
        print(f"Tidak ada versi sebelumnya untuk rollback (production sekarang: v{current}). Pakai VERSION=n.")
        return 1
    MlflowClient().get_model_version(model, str(target))  # gagal jelas bila versi tidak ada
    registry.set_production(engine, target, model=model)
    registry.mark_rolled_back(engine, current, model)
    print(f"Rollback {model}: production v{current} → v{target}. API memuat ulang otomatis dalam ≤ 30 detik.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
