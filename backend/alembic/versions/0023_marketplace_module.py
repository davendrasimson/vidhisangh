"""Marketplace module: listings and responses (global cross-tenant board).

Like the professional network, these tables are intentionally global (no
tenant_id scoping, no RLS).

Revision ID: 0023_marketplace
Revises: 0022_knowledge
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_marketplace"
down_revision: str | None = "0022_knowledge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = sa.Uuid(as_uuid=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "marketplace_listings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("type", sa.String(20), nullable=False, server_default="referral"),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("practice_area", sa.String(150), nullable=True),
        sa.Column("location", sa.String(200), nullable=True),
        sa.Column("budget", sa.Numeric(12, 2), nullable=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="open"),
        sa.Column("posted_by", UUID, nullable=False),
        sa.Column("poster_name", sa.String(200), nullable=False),
        sa.Column("poster_tenant_id", UUID, nullable=True),
        sa.Column("response_count", sa.Integer(), nullable=False, server_default="0"),
        *_timestamps(),
    )
    op.create_index("ix_marketplace_listings_type", "marketplace_listings", ["type"])
    op.create_index("ix_marketplace_listings_status", "marketplace_listings", ["status"])
    op.create_index("ix_marketplace_listings_practice_area", "marketplace_listings", ["practice_area"])
    op.create_index("ix_marketplace_listings_posted_by", "marketplace_listings", ["posted_by"])

    op.create_table(
        "marketplace_responses",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("listing_id", UUID, nullable=False),
        sa.Column("responder_id", UUID, nullable=False),
        sa.Column("responder_name", sa.String(200), nullable=False),
        sa.Column("responder_email", sa.String(320), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["listing_id"], ["marketplace_listings.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_marketplace_responses_listing_id", "marketplace_responses", ["listing_id"])
    op.create_index("ix_marketplace_responses_responder_id", "marketplace_responses", ["responder_id"])


def downgrade() -> None:
    op.drop_table("marketplace_responses")
    op.drop_table("marketplace_listings")
