"""Tahap 2 (Beta): tabel sensor_readings (bacaan MQ-2) dan sensor_nodes (baseline + status per node).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-21
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

STATES = "state IN ('warming_up', 'normal', 'alert')"


def upgrade() -> None:
    op.create_table(
        "sensor_nodes",
        sa.Column("node_id", sa.String(64), primary_key=True),
        sa.Column("baseline_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("baseline_kohm", sa.Float()),
        sa.Column("state", sa.String(20), server_default="warming_up", nullable=False),
        sa.Column("low_streak", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_uptime_s", sa.Integer()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(STATES, name="ck_sensor_nodes_state"),
    )
    op.create_table(
        "sensor_readings",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("node_id", sa.String(64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("mq2_rs_kohm", sa.Float(), nullable=False),
        sa.Column("uptime_s", sa.Integer()),
        sa.Column("ratio", sa.Float()),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("valid", sa.Boolean(), nullable=False),
        sa.Column("simulated", sa.Boolean(), server_default="false", nullable=False),
        sa.CheckConstraint(STATES, name="ck_sensor_readings_state"),
    )
    op.create_index("ix_sensor_readings_node_received", "sensor_readings", ["node_id", "received_at"])


def downgrade() -> None:
    op.drop_index("ix_sensor_readings_node_received", table_name="sensor_readings")
    op.drop_table("sensor_readings")
    op.drop_table("sensor_nodes")
