"""Tahap 3: tabel node_readings (node lengkap konsep dan simulatornya).

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-21
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "node_readings",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("node_id", sa.String(64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("uptime_s", sa.Integer()),
        *[sa.Column(c, sa.Float()) for c in ("smoke_prob", "co_ppm", "pm25", "pm10", "co2_ppm", "voc_index",
                                              "nox_index", "temp_c", "rh")],
        sa.Column("simulated", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_index("ix_node_readings_node_received", "node_readings", ["node_id", "received_at"])


def downgrade() -> None:
    op.drop_index("ix_node_readings_node_received", table_name="node_readings")
    op.drop_table("node_readings")
