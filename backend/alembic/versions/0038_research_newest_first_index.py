"""Index that serves the research list's newest-first ordering.

Revision ID: 0038_research_newest_first_index
Revises: 0037_research_statistics

`GET /research/judgments` with no query — the landing page — orders by
``judgment_date DESC NULLS LAST, created_at DESC``. The plain btree on
``judgment_date`` cannot serve that: scanned backwards it yields NULLS *first*,
so Postgres fell back to a parallel seq scan of all 5.6M rows plus a top-N sort
— 6.4 s measured on production, on every uncached landing load. An index whose
definition matches the ORDER BY exactly is read forwards and stops after 20
rows: 1.5 ms.

Built with CONCURRENTLY so the live API is not locked out of the table.
"""

from __future__ import annotations

from alembic import op

revision: str = "0038_research_newest_first_index"
down_revision: str | None = "0037_research_statistics"
branch_labels = None
depends_on = None

_NAME = "ix_judgments_newest_first"


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return  # SQLite tests use create_all; ordering there is over rows-of-ten.
    # CONCURRENTLY cannot run inside a transaction block.
    with op.get_context().autocommit_block():
        op.execute(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {_NAME} ON judgments "
            "(judgment_date DESC NULLS LAST, created_at DESC) WHERE deleted_at IS NULL"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {_NAME}")
