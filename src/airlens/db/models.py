"""Skema database. Setiap perubahan wajib disertai migrasi Alembic baru."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

PREDICTION_STATUSES = ("ok", "uncertain", "rejected")
MODEL_STAGES = ("candidate", "shadow", "production", "archived")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    pass


class IqairReading(Base):
    """Pembacaan AQI resmi IQAir (pembanding, bukan label latih)."""

    __tablename__ = "iqair_readings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    city: Mapped[str] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(100))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    aqi_us: Mapped[int | None] = mapped_column(Integer)
    main_pollutant: Mapped[str | None] = mapped_column(String(20))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (Index("ix_iqair_readings_city_fetched_at", "city", "fetched_at"),)


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(50))
    stage: Mapped[str] = mapped_column(String(20), server_default="candidate")
    mlflow_run_id: Mapped[str | None] = mapped_column(String(64))
    data_version: Mapped[str | None] = mapped_column(String(64))
    git_commit: Mapped[str | None] = mapped_column(String(40))
    confidence_threshold: Mapped[float | None] = mapped_column(Float)
    metrics: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_model_versions_name_version"),
        CheckConstraint(_in("stage", MODEL_STAGES), name="ck_model_versions_stage"),
    )


class Prediction(Base):
    """Satu baris per prediksi (termasuk prediksi shadow). Foto tidak disimpan, hanya hash dan statistik."""

    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    model_version: Mapped[str] = mapped_column(String(100))
    data_version: Mapped[str | None] = mapped_column(String(64))
    is_shadow: Mapped[bool] = mapped_column(Boolean, server_default="false")
    status: Mapped[str] = mapped_column(String(20))
    reject_reason: Mapped[str | None] = mapped_column(String(100))
    predicted_class: Mapped[str | None] = mapped_column(String(40))
    confidence: Mapped[float | None] = mapped_column(Float)
    probabilities: Mapped[dict | None] = mapped_column(JSONB)
    image_sha256: Mapped[str | None] = mapped_column(String(64))
    input_stats: Mapped[dict | None] = mapped_column(JSONB)
    city: Mapped[str | None] = mapped_column(String(100))
    iqair_aqi_us: Mapped[int | None] = mapped_column(Integer)
    iqair_reading_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("iqair_readings.id", ondelete="SET NULL")
    )
    latency_ms: Mapped[float | None] = mapped_column(Float)
    job_id: Mapped[str | None] = mapped_column(String(36))
    photo_stored: Mapped[bool] = mapped_column(Boolean, server_default="false")  # hanya dengan persetujuan pengguna

    __table_args__ = (
        CheckConstraint(_in("status", PREDICTION_STATUSES), name="ck_predictions_status"),
        Index("ix_predictions_created_at", "created_at"),
    )


class MonitoringReport(Base):
    __tablename__ = "monitoring_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    report_type: Mapped[str] = mapped_column(String(40))
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    metrics: Mapped[dict | None] = mapped_column(JSONB)
    alerts: Mapped[list | None] = mapped_column(JSONB)
    retrain_triggered: Mapped[bool] = mapped_column(Boolean, server_default="false")


class IqairRequest(Base):
    """Setiap panggilan ke API IQAir (berhasil atau gagal): dasar penghitungan kuota 5/menit dan 500/hari."""

    __tablename__ = "iqair_requests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    endpoint: Mapped[str] = mapped_column(String(40))
    ok: Mapped[bool] = mapped_column(Boolean)
    status_code: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (Index("ix_iqair_requests_requested_at", "requested_at"),)
