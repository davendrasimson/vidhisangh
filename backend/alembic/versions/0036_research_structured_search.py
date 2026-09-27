"""Research: structured registry fields + ranked full-text search.

Revision ID: 0036_research_structured_search
Revises: 0035_research_search_indexes
Create Date: 2026-09-23

The corpus (5.6M rows) could be *searched* but not *browsed*: case type was
buried in the title string, judges were inconsistent provider strings, and
search was an unranked substring match. This adds:

* ``case_type`` / ``case_number`` / ``case_year`` / ``cause_title`` — parsed
  from the registry title by ``app.scripts.backfill_case_fields`` (kept out of
  the migration: a 5.6M-row backfill belongs in a resumable, batched script).
* ``judge_text`` — judges normalised to bare names and joined, so "MR. JUSTICE
  X", "HON'BLE MR. JUSTICE X" and "Justice X" become one facet value.
* ``search_vector`` — a **stored, generated** tsvector Postgres maintains
  itself, weighted: title A, judges/court/case type B, headnote C, acts/keywords
  D. ``websearch_to_tsquery`` over it gives Google-style syntax (quotes,
  ``-exclude``, ``OR``) with relevance ranking. Generated columns cannot exist
  on SQLite, so the tests exercise an ILIKE fallback and the FTS path is
  covered by a Postgres-only test.

Operational note: adding a STORED generated column **rewrites the table under
an exclusive lock** — several minutes at 5.6M rows, during which research
reads and writes wait. Pause the enrichment job first. The GIN indexes are then
built CONCURRENTLY so the table is usable while they build.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036_research_structured_search"
down_revision: str | None = "0035_research_search_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

log = logging.getLogger("alembic.runtime.migration")

_SEARCH_VECTOR_EXPR = (
    "setweight(to_tsvector('english', coalesce(case_name, '')), 'A') || "
    "setweight(to_tsvector('english', coalesce(judge_text, '') || ' ' || "
    "                                  coalesce(court, '') || ' ' || "
    "                                  coalesce(case_type, '')), 'B') || "
    "setweight(to_tsvector('english', coalesce(headnote, '')), 'C') || "
    "setweight(to_tsvector('english', coalesce(acts::text, '') || ' ' || "
    "                                  coalesce(keywords::text, '')), 'D')"
)


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    op.add_column("judgments", sa.Column("case_type", sa.String(40), nullable=True))
    op.add_column("judgments", sa.Column("case_number", sa.String(40), nullable=True))
    op.add_column("judgments", sa.Column("case_year", sa.Integer(), nullable=True))
    op.add_column("judgments", sa.Column("cause_title", sa.String(500), nullable=True))
    op.add_column("judgments", sa.Column("judge_text", sa.Text(), nullable=True))
    op.create_index("ix_judgments_case_type", "judgments", ["case_type"])
    op.create_index("ix_judgments_case_year", "judgments", ["case_year"])
    op.create_index("ix_judgments_court", "judgments", ["court"])

    if not is_pg:
        return

    # Table rewrite — see the module docstring.
    op.execute(
        f"ALTER TABLE judgments ADD COLUMN search_vector tsvector "
        f"GENERATED ALWAYS AS ({_SEARCH_VECTOR_EXPR}) STORED"
    )

    has_trgm = bind.exec_driver_sql(
        "SELECT count(*) FROM pg_extension WHERE extname = 'pg_trgm'"
    ).scalar()

    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_judgments_search_vector "
            "ON judgments USING gin (search_vector)"
        )
        if has_trgm:
            op.execute(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_judgments_judge_text_trgm "
                "ON judgments USING gin (judge_text gin_trgm_ops)"
            )
        else:
            log.warning("pg_trgm missing — judge substring filter will not be indexed")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_judgments_judge_text_trgm")
            op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_judgments_search_vector")
        op.execute("ALTER TABLE judgments DROP COLUMN IF EXISTS search_vector")
    op.drop_index("ix_judgments_court", table_name="judgments")
    op.drop_index("ix_judgments_case_year", table_name="judgments")
    op.drop_index("ix_judgments_case_type", table_name="judgments")
    for col in ("judge_text", "cause_title", "case_year", "case_number", "case_type"):
        op.drop_column("judgments", col)
