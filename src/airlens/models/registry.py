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


class _NoDB:
    """Pengganti Session dan baris saat AIRLENS_DB=none: semua operasi diserap (atribut, panggilan, iterasi kosong)."""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, name):
        return self

    def __setattr__(self, name, value):
        pass

    def __call__(self, *a, **k):
        return self

    def __iter__(self):
        return iter(())

    def __bool__(self):
        return False


def _session(engine):
    return _NoDB() if engine is None else Session(engine)


def alias_version(alias: str, client: MlflowClient | None = None, model: str = REGISTERED_MODEL) -> str | None:
    try:
        return str((client or MlflowClient()).get_model_version_by_alias(model, alias).version)  # SQLite: int
    except Exception:  # alias belum ada
        return None


def _upsert(s: Session, version: str, model: str = REGISTERED_MODEL, **fields) -> ModelVersion | None:
    if isinstance(s, _NoDB):
        return s
    row = s.scalars(select(ModelVersion).where(ModelVersion.name == model,
                                               ModelVersion.version == str(version))).first()
    if row is None:
        row = ModelVersion(name=model, version=str(version))
        s.add(row)
    for k, v in fields.items():
        setattr(row, k, v)
    return row


def record_registration(engine: Engine, version: str, stage: str, meta: dict, model: str = REGISTERED_MODEL,
                        metric_keys: tuple[str, ...] = ("macro_f1", "balanced_accuracy", "ece")) -> None:
    with _session(engine) as s:
        _upsert(s, version, model, stage=stage, mlflow_run_id=meta.get("mlflow_run_id"),
                data_version=meta.get("data_version"), git_commit=(meta.get("git_commit") or "")[:40],
                confidence_threshold=(meta.get("threshold") or {}).get("threshold"),
                metrics={k: meta["val_metrics"].get(k) for k in metric_keys}
                | {"code_version": meta.get("code_version"), "smoke": meta.get("smoke", False)})
        s.commit()


def set_production(engine: Engine, version: str, client: MlflowClient | None = None,
                   model: str = REGISTERED_MODEL) -> str | None:
    """Pindahkan alias production ke `version`; kembalikan versi production sebelumnya. Riwayat dicatat di db."""
    client = client or MlflowClient()
    previous = alias_version("production", client, model)
    client.set_registered_model_alias(model, "production", str(version))
    now = datetime.now(timezone.utc)
    with _session(engine) as s:
        if previous and previous != str(version):
            _upsert(s, previous, model, stage="archived")
        row = _upsert(s, version, model, stage="production", promoted_at=now)
        row.metrics = {**(row.metrics or {}), "rolled_back": False}  # dipromosikan lagi: bukan versi yang ditarik
        s.commit()
    return previous


def mark_rolled_back(engine: Engine, version: str, model: str = REGISTERED_MODEL) -> None:
    """Tandai versi yang ditarik lewat rollback agar rollback berikutnya tidak kembali ke versi itu."""
    with _session(engine) as s:
        row = _upsert(s, version, model, stage="archived")
        row.metrics = {**(row.metrics or {}), "rolled_back": True}
        s.commit()


def set_challenger(engine: Engine, version: str, client: MlflowClient | None = None,
                   model: str = REGISTERED_MODEL) -> None:
    (client or MlflowClient()).set_registered_model_alias(model, "challenger", str(version))
    with _session(engine) as s:
        _upsert(s, version, model, stage="shadow")
        s.commit()


def clear_challenger(client: MlflowClient | None = None, model: str = REGISTERED_MODEL) -> None:
    try:
        (client or MlflowClient()).delete_registered_model_alias(model, "challenger")
    except Exception:
        pass


def previous_production(engine: Engine, current: str, model: str = REGISTERED_MODEL) -> str | None:
    """Versi production terakhir sebelum `current` (riwayat promoted_at), melewati versi yang pernah di-rollback."""
    with _session(engine) as s:
        rows = s.scalars(select(ModelVersion).where(ModelVersion.name == model,
                                                    ModelVersion.promoted_at.is_not(None),
                                                    ModelVersion.version != str(current))
                         .order_by(ModelVersion.promoted_at.desc())).all()
    rows = [r for r in (rows or []) if not (r.metrics or {}).get("rolled_back")]
    return rows[0].version if rows else None


def download_bundle(version: str, dest_root, model: str = REGISTERED_MODEL) -> "Path":
    """Unduh model ONNX + metadata.json versi registry ke dest_root/v<versi>/ (dipakai promote dan simulasi)."""
    from pathlib import Path

    import mlflow

    client = MlflowClient()
    mv = client.get_model_version(model, str(version))
    dest = Path(dest_root) / (f"v{version}" if model == REGISTERED_MODEL else f"{model}-v{version}")
    if not (dest / "metadata.json").exists():
        dest.mkdir(parents=True, exist_ok=True)
        mlflow.artifacts.download_artifacts(artifact_uri=f"models:/{model}/{version}", dst_path=str(dest / "model"))
        meta = Path(mlflow.artifacts.download_artifacts(run_id=mv.run_id, artifact_path="bundle/metadata.json",
                                                        dst_path=str(dest / "meta")))
        meta.rename(dest / "metadata.json")
    return dest
