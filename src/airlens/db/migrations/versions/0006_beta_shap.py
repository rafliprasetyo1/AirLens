"""Revisi Beta SHAP: bacaan 4 MQ (mV), fitur, keluaran model gas Beta + SHAP, shadow challenger, baseline per sensor.

Format lama (mq2_rs_kohm) tetap diterima, jadi kolom itu kini boleh kosong.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-21
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("sensor_readings", "mq2_rs_kohm", existing_type=sa.Float(), nullable=True)
    for c in ("mq2_mv", "mq3_mv", "mq7_mv", "mq135_mv"):
        op.add_column("sensor_readings", sa.Column(c, sa.Float()))
    op.add_column("sensor_readings", sa.Column("features", JSONB()))
    op.add_column("sensor_readings", sa.Column("predicted_class", sa.String(20)))
    op.add_column("sensor_readings", sa.Column("probs", JSONB()))
    op.add_column("sensor_readings", sa.Column("shap", JSONB()))
    op.add_column("sensor_readings", sa.Column("reason", sa.Text()))
    op.add_column("sensor_readings", sa.Column("model_version", sa.String(64)))
    op.add_column("sensor_readings", sa.Column("challenger_class", sa.String(20)))
    op.add_column("sensor_nodes", sa.Column("baseline_rs", JSONB()))
    op.add_column("sensor_nodes", sa.Column("alert_label", sa.String(20)))


def downgrade() -> None:
    op.drop_column("sensor_nodes", "alert_label")
    op.drop_column("sensor_nodes", "baseline_rs")
    for c in ("challenger_class", "model_version", "reason", "shap", "probs", "predicted_class", "features",
              "mq135_mv", "mq7_mv", "mq3_mv", "mq2_mv"):
        op.drop_column("sensor_readings", c)
    op.execute("DELETE FROM sensor_readings WHERE mq2_rs_kohm IS NULL")
    op.alter_column("sensor_readings", "mq2_rs_kohm", existing_type=sa.Float(), nullable=False)
