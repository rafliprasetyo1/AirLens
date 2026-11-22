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
    Text,
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


SENSOR_STATES = ("warming_up", "normal", "alert")


class SensorNode(Base):
    """Status per node Beta: baseline Rs udara bersih dan hitungan histeresis (tahan restart API)."""

    __tablename__ = "sensor_nodes"

    node_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    baseline_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # awal pemanasan / reset terakhir
    baseline_kohm: Mapped[float | None] = mapped_column(Float)
    state: Mapped[str] = mapped_column(String(20), server_default="warming_up")
    low_streak: Mapped[int] = mapped_column(Integer, server_default="0")
    last_uptime_s: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Revisi Beta SHAP: baseline Rs per sensor {"MQ2": kΩ, ...} dan label alert dari model ("smoke"/"alcohol").
    baseline_rs: Mapped[dict | None] = mapped_column(JSONB)
    alert_label: Mapped[str | None] = mapped_column(String(20))

    __table_args__ = (CheckConstraint(_in("state", SENSOR_STATES), name="ck_sensor_nodes_state"),)


class SensorReading(Base):
    """Satu bacaan MQ-2 dari node Beta (atau simulator). received_at = waktu server, bukan waktu perangkat."""

    __tablename__ = "sensor_readings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    node_id: Mapped[str] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    mq2_rs_kohm: Mapped[float | None] = mapped_column(Float)   # format lama; format baru: Rs MQ-2 hasil hitung
    uptime_s: Mapped[int | None] = mapped_column(Integer)
    ratio: Mapped[float | None] = mapped_column(Float)              # Rs/baseline MQ-2
    state: Mapped[str] = mapped_column(String(20))
    valid: Mapped[bool] = mapped_column(Boolean)
    simulated: Mapped[bool] = mapped_column(Boolean, server_default="false")
    # Revisi Beta SHAP (format 4 MQ): tegangan pin ADC (mV), fitur rasio, keluaran model, SHAP, shadow challenger.
    mq2_mv: Mapped[float | None] = mapped_column(Float)
    mq3_mv: Mapped[float | None] = mapped_column(Float)
    mq7_mv: Mapped[float | None] = mapped_column(Float)
    mq135_mv: Mapped[float | None] = mapped_column(Float)
    features: Mapped[dict | None] = mapped_column(JSONB)
    predicted_class: Mapped[str | None] = mapped_column(String(20))
    probs: Mapped[dict | None] = mapped_column(JSONB)
    shap: Mapped[dict | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str | None] = mapped_column(String(64))
    challenger_class: Mapped[str | None] = mapped_column(String(20))

    __table_args__ = (
        CheckConstraint(_in("state", SENSOR_STATES), name="ck_sensor_readings_state"),
        Index("ix_sensor_readings_node_received", "node_id", "received_at"),
    )


class NodeReading(Base):
    """Bacaan node lengkap (konsep: Pi 5 + SEN66 + CO-B4 + kamera) atau simulatornya. Node hanya mengirim angka."""

    __tablename__ = "node_readings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    node_id: Mapped[str] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    uptime_s: Mapped[int | None] = mapped_column(Integer)
    smoke_prob: Mapped[float | None] = mapped_column(Float)
    co_ppm: Mapped[float | None] = mapped_column(Float)
    pm25: Mapped[float | None] = mapped_column(Float)
    pm10: Mapped[float | None] = mapped_column(Float)
    co2_ppm: Mapped[float | None] = mapped_column(Float)
    voc_index: Mapped[float | None] = mapped_column(Float)   # indeks Sensirion, bukan ppm
    nox_index: Mapped[float | None] = mapped_column(Float)   # indeks Sensirion, bukan ppm
    temp_c: Mapped[float | None] = mapped_column(Float)
    rh: Mapped[float | None] = mapped_column(Float)
    simulated: Mapped[bool] = mapped_column(Boolean, server_default="false")

    __table_args__ = (Index("ix_node_readings_node_received", "node_id", "received_at"),)


EVENT_KINDS = ("smoke_confirmed", "invisible_gas", "visible_smoke", "back_to_normal")
EVENT_PRIORITIES = ("high", "medium", "info")


class Event(Base):
    """Kejadian dari trigger engine (dua pemicu: kamera + gas) per ruangan."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    room: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(32))
    priority: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(String(300))
    sources: Mapped[list | None] = mapped_column(JSONB)   # sumber yang aktif saat kejadian
    trigger_values: Mapped[dict | None] = mapped_column(JSONB)   # nilai pemicu (mis. co_ppm, smoke_prob median)
    simulated: Mapped[bool] = mapped_column(Boolean, server_default="false")

    __table_args__ = (
        CheckConstraint(_in("kind", EVENT_KINDS), name="ck_events_kind"),
        CheckConstraint(_in("priority", EVENT_PRIORITIES), name="ck_events_priority"),
        Index("ix_events_room_created", "room", "created_at"),
    )


class IqairRequest(Base):
    """Setiap panggilan ke API IQAir (berhasil atau gagal): dasar penghitungan kuota 5/menit dan 500/hari."""

    __tablename__ = "iqair_requests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    endpoint: Mapped[str] = mapped_column(String(40))
    ok: Mapped[bool] = mapped_column(Boolean)
    status_code: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (Index("ix_iqair_requests_requested_at", "requested_at"),)


class PushSubscription(Base):
    """Langganan Web Push dari browser yang menekan "Enable alerts". Hanya endpoint + kunci browser (tanpa data
    pribadi lain); dihapus lewat "Disable alerts" atau otomatis saat layanan push menjawab 404/410."""

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
