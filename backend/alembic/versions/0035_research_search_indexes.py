"""Research search: trigram indexes on every searched column.

Revision ID: 0035_research_search_indexes
Revises: 0034_high_court_orders
Create Date: 2026-09-23

0034 added a trigram index on ``case_name`` only. That is not what the search
actually filters on: ``JudgmentRepository.search`` ORs across ``case_name``,
``citation``, ``headnote`` and ``keywords``, and a single index cannot serve
that OR. With 5.6M rows the planner fell back to walking the ``judgment_date``
index backwards and filtering **5,664,584 rows** — 26 seconds per query.

With all four indexed, Postgres builds a BitmapOr across them: the same query
drops to ~28 ms (API latency 31.5 s → 0.15 s).

These match ``ILIKE`` (what SQLAlchemy emits on PostgreSQL). An index on the
bare column does NOT serve ``lower(col) LIKE …``; if the repository is ever
changed to that form, these indexes silently stop being used and the scans
come back.

Built with CONCURRENTLY so a live deployment is not locked out of the table,
which means each statement runs outside the migration's transaction.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from alembic import op

revision: str = "0035_research_search_indexes"
down_revision: str | None = "0034_high_court_orders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

log = logging.getLogger("alembic.runtime.migration")

_INDEXES = {
    "ix_judgments_citation_trgm": "citation gin_trgm_ops",
    "ix_judgments_headnote_trgm": "headnote gin_trgm_ops",
    "ix_judgments_keywords_trgm": "(keywords::varchar) gin_trgm_ops",
}


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # trigram indexes are a Postgres-only concern

    has_trgm = bind.exec_driver_sql(
        "SELECT count(*) FROM pg_extension WHERE extname = 'pg_trgm'"
    ).scalar()
    if not has_trgm:
        log.warning(
            "pg_trgm is not installed — skipping research search indexes. "
            "Install it (as superuser) and re-run: "
            "CREATE EXTENSION pg_trgm; then this migration."
        )
        return

    # CONCURRENTLY cannot run inside a transaction block.
    with op.get_context().autocommit_block():
        for name, expression in _INDEXES.items():
            op.execute(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} "
                f"ON judgments USING gin ({expression})"
            )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    with op.get_context().autocommit_block():
        for name in _INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
