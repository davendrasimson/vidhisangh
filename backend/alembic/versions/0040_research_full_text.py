"""Full text of orders/judgments, searchable, without rewriting the table.

Revision ID: 0040_research_full_text
Revises: 0039_research_case_parties

Text extracted from the order PDFs (``app.scripts.extract_order_text``) lands in
``full_text``. It is deliberately NOT folded into the generated ``search_vector``
(0036): changing a STORED generated column rewrites all 5.6M rows under an
ACCESS EXCLUSIVE lock — the research outage of the 0036 deploy. Instead the
full text gets its own GIN *expression* index, built CONCURRENTLY, and the
search ORs the two vectors; Postgres BitmapOr's both indexes, exactly as the
four trigram indexes are combined (0035).

Only the first 300,000 characters (~50 pages) are indexed: a tsvector is capped
at 1 MB and a 200-page judgment could exceed it. The whole text is stored.
The expression here must match ``ResearchRepository._FULL_TEXT_VECTOR``
character for character, or the planner will not use the index.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0040_research_full_text"
down_revision: str | None = "0039_research_case_parties"
branch_labels = None
depends_on = None

_INDEX = "ix_judgments_full_text_fts"
FULL_TEXT_VECTOR_SQL = "to_tsvector('english'::regconfig, left(coalesce(full_text, ''), 300000))"


def upgrade() -> None:
    op.add_column("judgments", sa.Column("full_text", sa.Text(), nullable=True))
    op.add_column(
        "judgments", sa.Column("text_extracted_at", sa.DateTime(timezone=True), nullable=True)
    )
    if op.get_bind().dialect.name != "postgresql":
        return
    # CONCURRENTLY cannot run inside a transaction block.
    with op.get_context().autocommit_block():
        op.execute(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {_INDEX} ON judgments "
            f"USING gin ({FULL_TEXT_VECTOR_SQL})"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {_INDEX}")
    op.drop_column("judgments", "text_extracted_at")
    op.drop_column("judgments", "full_text")
