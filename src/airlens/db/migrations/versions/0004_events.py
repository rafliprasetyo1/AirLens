"""Tahap 3: tabel events (kejadian trigger engine dua pemicu).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-21
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("room", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("message", sa.String(300), nullable=False),
        sa.Column("sources", JSONB()),
        sa.Column("trigger_values", JSONB()),
        sa.Column("simulated", sa.Boolean(), server_default="false", nullable=False),
        sa.CheckConstraint("kind IN ('smoke_confirmed', 'invisible_gas', 'visible_smoke', 'back_to_normal')",
                           name="ck_events_kind"),
        sa.CheckConstraint("priority IN ('high', 'medium', 'info')", name="ck_events_priority"),
    )
    op.create_index("ix_events_room_created", "events", ["room", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_events_room_created", table_name="events")
    op.drop_table("events")
