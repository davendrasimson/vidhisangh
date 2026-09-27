"""Legal news module: a shared cross-tenant news feed (global table).

Revision ID: 0018_news
Revises: 0017_research
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_news"
down_revision: str | None = "0017_research"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = sa.Uuid(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "news_items",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("title", sa.String(400), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("source", sa.String(150), nullable=False),
        sa.Column("category", sa.String(20), nullable=False, server_default="news"),
        sa.Column("url", sa.String(600), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("added_by", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_news_items_source", "news_items", ["source"])
    op.create_index("ix_news_items_category", "news_items", ["category"])
    op.create_index("ix_news_items_published_at", "news_items", ["published_at"])


def downgrade() -> None:
    op.drop_table("news_items")
