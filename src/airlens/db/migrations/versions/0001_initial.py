"""Skema awal: predictions, iqair_readings, model_versions, monitoring_reports.

Revision ID: 0001
Revises:
Create Date: 2026-10-24
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "iqair_readings",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("state", sa.String(100)),
        sa.Column("country", sa.String(100)),
        sa.Column("lat", sa.Float()),
        sa.Column("lon", sa.Float()),
        sa.Column("aqi_us", sa.Integer()),
        sa.Column("main_pollutant", sa.String(20)),
        sa.Column("observed_at", sa.DateTime(timezone=True)),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("raw", JSONB()),
    )
    op.create_index("ix_iqair_readings_city_fetched_at", "iqair_readings", ["city", "fetched_at"])

    op.create_table(
        "model_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("stage", sa.String(20), server_default="candidate", nullable=False),
        sa.Column("mlflow_run_id", sa.String(64)),
        sa.Column("data_version", sa.String(64)),
        sa.Column("git_commit", sa.String(40)),
        sa.Column("confidence_threshold", sa.Float()),
        sa.Column("metrics", JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("name", "version", name="uq_model_versions_name_version"),
        sa.CheckConstraint(
            "stage IN ('candidate', 'shadow', 'production', 'archived')", name="ck_model_versions_stage"
        ),
    )

    op.create_table(
        "predictions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("model_version", sa.String(100), nullable=False),
        sa.Column("data_version", sa.String(64)),
        sa.Column("is_shadow", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reject_reason", sa.String(100)),
        sa.Column("predicted_class", sa.String(40)),
        sa.Column("confidence", sa.Float()),
        sa.Column("probabilities", JSONB()),
        sa.Column("image_sha256", sa.String(64)),
        sa.Column("input_stats", JSONB()),
        sa.Column("city", sa.String(100)),
        sa.Column("iqair_aqi_us", sa.Integer()),
        sa.Column(
            "iqair_reading_id", sa.BigInteger(), sa.ForeignKey("iqair_readings.id", ondelete="SET NULL")
        ),
        sa.Column("latency_ms", sa.Float()),
        sa.CheckConstraint("status IN ('ok', 'uncertain', 'rejected')", name="ck_predictions_status"),
    )
    op.create_index("ix_predictions_created_at", "predictions", ["created_at"])

    op.create_table(
        "monitoring_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("report_type", sa.String(40), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metrics", JSONB()),
        sa.Column("alerts", JSONB()),
        sa.Column("retrain_triggered", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_table("monitoring_reports")
    op.drop_index("ix_predictions_created_at", table_name="predictions")
    op.drop_table("predictions")
    op.drop_table("model_versions")
    op.drop_index("ix_iqair_readings_city_fetched_at", table_name="iqair_readings")
    op.drop_table("iqair_readings")
