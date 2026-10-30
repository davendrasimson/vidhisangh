"""Matter-board attention digest: one send record per member per day.

Revision ID: 0081_board_digest_sends
Revises: 0080_judgment_aliases

Like ``hearing_reminder_sends`` (0068): the row is claimed before sending, so a
rerun of the morning job never sends the same digest twice. Global table — a
member's digest spans the matters they are on, within their own tenant.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0081_board_digest_sends"
down_revision = "0080_judgment_aliases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "board_digest_sends",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("for_date", sa.Date(), nullable=False),
        sa.Column("matter_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("detail", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "for_date", name="uq_board_digest_user_day"),
    )
    op.create_index("ix_board_digest_sends_user_id", "board_digest_sends", ["user_id"])


def downgrade() -> None:
    op.drop_table("board_digest_sends")
