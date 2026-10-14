"""Invite links: a personal referral code per user, and the sign-ups it brought.

Global tables (no RLS), like the network tables: the inviter and the person who
joins are in different organisations. Only user ids are stored.

Revision ID: 0065_referrals
Revises: 0064_ai_headnotes
"""

import sqlalchemy as sa

from alembic import op

revision = "0065_referrals"
down_revision = "0064_ai_headnotes"
branch_labels = None
depends_on = None

UUID = sa.Uuid(as_uuid=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "referral_codes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("user_id", name="uq_referral_codes_user"),
        sa.UniqueConstraint("code", name="uq_referral_codes_code"),
    )
    op.create_table(
        "referrals",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("referrer_user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("referred_user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("referred_user_id", name="uq_referrals_referred"),
    )
    op.create_index("ix_referrals_referrer_user_id", "referrals", ["referrer_user_id"])


def downgrade() -> None:
    op.drop_table("referrals")
    op.drop_table("referral_codes")
