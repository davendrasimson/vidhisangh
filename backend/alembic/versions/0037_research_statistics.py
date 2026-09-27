"""Research: better planner statistics for the full-text and judge columns.

Revision ID: 0037_research_statistics
Revises: 0036_research_structured_search
Create Date: 2026-09-23

With the default statistics target (100), the planner's row estimates for
``search_vector @@ query`` were badly low on the 5.6M-row corpus — 17,900
estimated against 126,770 actual for "anticipatory bail", 5,618 against 142,752
for a phrase query. Two things depend on those estimates being roughly right:
the "About N results" path (which never engaged) and plan choice for broad
queries. tsvector statistics are most-common-element lists, so a larger target
directly improves them. Cost is a slower ANALYZE, which is fine.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0037_research_statistics"
down_revision: str | None = "0036_research_structured_search"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE judgments ALTER COLUMN search_vector SET STATISTICS 1000")
    op.execute("ALTER TABLE judgments ALTER COLUMN judge_text SET STATISTICS 500")
    op.execute("ALTER TABLE judgments ALTER COLUMN case_type SET STATISTICS 500")
    op.execute("ANALYZE judgments")


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for col in ("search_vector", "judge_text", "case_type"):
        op.execute(f"ALTER TABLE judgments ALTER COLUMN {col} SET STATISTICS -1")
