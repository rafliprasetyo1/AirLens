"""Fase 4: job_id dan photo_stored di predictions; tabel iqair_requests untuk kuota IQAir.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-25
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("predictions", sa.Column("job_id", sa.String(36)))
    op.add_column("predictions", sa.Column("photo_stored", sa.Boolean(), server_default="false", nullable=False))
    op.create_table(
        "iqair_requests",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("endpoint", sa.String(40), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("status_code", sa.Integer()),
    )
    op.create_index("ix_iqair_requests_requested_at", "iqair_requests", ["requested_at"])


def downgrade() -> None:
    op.drop_index("ix_iqair_requests_requested_at", table_name="iqair_requests")
    op.drop_table("iqair_requests")
    op.drop_column("predictions", "photo_stored")
    op.drop_column("predictions", "job_id")
