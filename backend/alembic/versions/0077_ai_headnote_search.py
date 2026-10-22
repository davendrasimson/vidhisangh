"""Search inside AI headnotes: a partial GIN index over their text.

Revision ID: 0077_ai_headnote_search
Revises: 0076_invoice_tax_position

Only judgments with an AI headnote (about 2,000 of 5.6M today) are indexed, so
the index is small; building it CONCURRENTLY scans the table without blocking
writes. The expression and predicate must match
``ResearchRepository._AI_HEADNOTE_VECTOR`` (and its ``ai_headnote IS NOT NULL``)
exactly, or the planner will not use it. Expression checked as immutable on
production first (22 Oct 2026).
"""

from __future__ import annotations

from alembic import op

revision: str = "0077_ai_headnote_search"
down_revision: str | None = "0076_invoice_tax_position"
branch_labels = None
depends_on = None

_INDEX = "ix_judgments_ai_headnote_fts"
# Copied from app.modules.research.repository.AI_HEADNOTE_VECTOR_SQL (a
# migration must not import app code that may change later).
AI_HEADNOTE_VECTOR_SQL = (
    "to_tsvector('english'::regconfig, "
    "coalesce(ai_headnote->>'summary', '') || ' ' || coalesce((ai_headnote->'issues')::text, '') || ' ' || "
    "coalesce((ai_headnote->'held')::text, '') || ' ' || coalesce((ai_headnote->'provisions')::text, ''))"
)


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    with op.get_context().autocommit_block():
        op.execute(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {_INDEX} ON judgments "
            f"USING gin ({AI_HEADNOTE_VECTOR_SQL}) WHERE ai_headnote IS NOT NULL"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {_INDEX}")
