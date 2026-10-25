"""Registry model: alias MLflow (`production`, `challenger`) + riwayat di tabel model_versions.

- `make train`   : daftarkan versi baru langsung sebagai production (bootstrap / pelatihan penuh).
- `make retrain` : daftarkan sebagai challenger -> API menjalankannya dalam shadow mode.
- `make promote` : challenger -> production bila kriteria terpenuhi; production lama -> archived.
- `make rollback`: production -> versi production sebelumnya (atau VERSION=n), tanpa build ulang.
API memeriksa alias secara berkala dan memuat ulang sendiri saat alias berpindah.
"""

from datetime import datetime, timezone

from mlflow import MlflowClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from airlens.db.models import ModelVersion

REGISTERED_MODEL = "airlens-aqi"


def alias_version(alias: str, client: MlflowClient | None = None) -> str | None:
    try:
        return (client or MlflowClient()).get_model_version_by_alias(REGISTERED_MODEL, alias).version
    except Exception:  # alias belum ada
        return None


def _upsert(s: Session, version: str, **fields) -> ModelVersion:
    row = s.scalars(select(ModelVersion).where(ModelVersion.name == REGISTERED_MODEL,
                                               ModelVersion.version == str(version))).first()
    if row is None:
        row = ModelVersion(name=REGISTERED_MODEL, version=str(version))
        s.add(row)
    for k, v in fields.items():
        setattr(row, k, v)
    return row


def record_registration(engine: Engine, version: str, stage: str, meta: dict) -> None:
    with Session(engine) as s:
        _upsert(s, version, stage=stage, mlflow_run_id=meta.get("mlflow_run_id"), data_version=meta.get("data_version"),
                git_commit=(meta.get("git_commit") or "")[:40], confidence_threshold=meta["threshold"]["threshold"],
                metrics={k: meta["val_metrics"].get(k) for k in ("macro_f1", "balanced_accuracy", "ece")}
                | {"code_version": meta.get("code_version"), "smoke": meta.get("smoke", False)})
        s.commit()


def set_production(engine: Engine, version: str, client: MlflowClient | None = None) -> str | None:
    """Pindahkan alias production ke `version`; kembalikan versi production sebelumnya. Riwayat dicatat di db."""
    client = client or MlflowClient()
    previous = alias_version("production", client)
    client.set_registered_model_alias(REGISTERED_MODEL, "production", str(version))
    now = datetime.now(timezone.utc)
    with Session(engine) as s:
        if previous and previous != str(version):
            _upsert(s, previous, stage="archived")
        row = _upsert(s, version, stage="production", promoted_at=now)
        row.metrics = {**(row.metrics or {}), "rolled_back": False}  # dipromosikan lagi: bukan versi yang ditarik
        s.commit()
    return previous


def mark_rolled_back(engine: Engine, version: str) -> None:
    """Tandai versi yang ditarik lewat rollback agar rollback berikutnya tidak kembali ke versi itu."""
    with Session(engine) as s:
        row = _upsert(s, version, stage="archived")
        row.metrics = {**(row.metrics or {}), "rolled_back": True}
        s.commit()


def set_challenger(engine: Engine, version: str, client: MlflowClient | None = None) -> None:
    (client or MlflowClient()).set_registered_model_alias(REGISTERED_MODEL, "challenger", str(version))
    with Session(engine) as s:
        _upsert(s, version, stage="shadow")
        s.commit()


def clear_challenger(client: MlflowClient | None = None) -> None:
    try:
        (client or MlflowClient()).delete_registered_model_alias(REGISTERED_MODEL, "challenger")
    except Exception:
        pass


def previous_production(engine: Engine, current: str) -> str | None:
    """Versi production terakhir sebelum `current` (riwayat promoted_at), melewati versi yang pernah di-rollback."""
    with Session(engine) as s:
        rows = s.scalars(select(ModelVersion).where(ModelVersion.name == REGISTERED_MODEL,
                                                    ModelVersion.promoted_at.is_not(None),
                                                    ModelVersion.version != str(current))
                         .order_by(ModelVersion.promoted_at.desc())).all()
    rows = [r for r in rows if not (r.metrics or {}).get("rolled_back")]
    return rows[0].version if rows else None


def download_bundle(version: str, dest_root) -> "Path":
    """Unduh model ONNX + metadata.json versi registry ke dest_root/v<versi>/ (dipakai promote dan simulasi)."""
    from pathlib import Path

    import mlflow

    client = MlflowClient()
    mv = client.get_model_version(REGISTERED_MODEL, str(version))
    dest = Path(dest_root) / f"v{version}"
    if not (dest / "metadata.json").exists():
        dest.mkdir(parents=True, exist_ok=True)
        mlflow.artifacts.download_artifacts(artifact_uri=f"models:/{REGISTERED_MODEL}/{version}", dst_path=str(dest / "model"))
        meta = Path(mlflow.artifacts.download_artifacts(run_id=mv.run_id, artifact_path="bundle/metadata.json",
                                                        dst_path=str(dest / "meta")))
        meta.rename(dest / "metadata.json")
    return dest
