"""Tahap 4: tabel push_subscriptions untuk Web Push (notifikasi kejadian saat website tertutup).

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-22
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("endpoint", sa.Text(), nullable=False, unique=True),
        sa.Column("p256dh", sa.String(200), nullable=False),
        sa.Column("auth", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_ok_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("push_subscriptions")
