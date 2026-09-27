"""Legal research module: judgments corpus and case-citation graph.

A shared, cross-tenant reference library — like the professional network, these
tables are intentionally global (no tenant_id, no RLS).

Revision ID: 0017_research
Revises: 0016_limitation
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_research"
down_revision: str | None = "0016_limitation"
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
        "judgments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("case_name", sa.String(500), nullable=False),
        sa.Column("citation", sa.String(200), nullable=False),
        sa.Column("neutral_citation", sa.String(200), nullable=True),
        sa.Column("court", sa.String(200), nullable=False),
        sa.Column("court_level", sa.String(20), nullable=False, server_default="other"),
        sa.Column("bench", sa.String(120), nullable=True),
        sa.Column("judges", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("judgment_date", sa.Date(), nullable=True),
        sa.Column("acts", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("sections", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("keywords", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("headnote", sa.Text(), nullable=True),
        sa.Column("outcome", sa.String(300), nullable=True),
        sa.Column("url", sa.String(500), nullable=True),
        sa.Column("added_by", UUID, nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("citation", name="judgment_citation"),
    )
    op.create_index("ix_judgments_citation", "judgments", ["citation"])
    op.create_index("ix_judgments_court_level", "judgments", ["court_level"])
    op.create_index("ix_judgments_judgment_date", "judgments", ["judgment_date"])

    op.create_table(
        "case_citations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("from_judgment_id", UUID, nullable=False),
        sa.Column("to_judgment_id", UUID, nullable=True),
        sa.Column("external_citation", sa.String(200), nullable=True),
        sa.Column("relationship_type", sa.String(20), nullable=False, server_default="referred"),
        sa.Column("added_by", UUID, nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["from_judgment_id"], ["judgments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_judgment_id"], ["judgments.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_case_citations_from_judgment_id", "case_citations", ["from_judgment_id"])
    op.create_index("ix_case_citations_to_judgment_id", "case_citations", ["to_judgment_id"])


def downgrade() -> None:
    op.drop_table("case_citations")
    op.drop_table("judgments")
