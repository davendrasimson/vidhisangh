"""Case parties, advocates and filing date on judgments.

Revision ID: 0039_research_case_parties
Revises: 0038_research_newest_first_index

An order record so far held a title, a CNR, a date, a judge and a fragment.
The registry data carries more that was dropped at ingest:

* ``date_of_registration`` — the filing date (100% of High Court rows).
* The two sides — in every cause title ("A Vs B").
* Counsel — Delhi prints "…Appellant Through: Mr. X, Advocate versus …
  Respondents Through: Ms. Y" in the order's opening (96% of its rows).

``advocate_text`` is the filter/facet column (like ``judge_text``): all
advocates on the record, " | "-joined, with a trigram index for ILIKE. The
column adds are metadata-only (nullable / constant default) so they do not
rewrite the 5.6M-row table; the index is built CONCURRENTLY.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0039_research_case_parties"
down_revision: str | None = "0038_research_newest_first_index"
branch_labels = None
depends_on = None

_TRGM = "ix_judgments_advocate_text_trgm"


def upgrade() -> None:
    op.add_column("judgments", sa.Column("filed_on", sa.Date(), nullable=True))
    op.add_column("judgments", sa.Column("petitioner", sa.String(300), nullable=True))
    op.add_column("judgments", sa.Column("respondent", sa.String(300), nullable=True))
    op.add_column(
        "judgments",
        sa.Column("petitioner_advocates", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "judgments",
        sa.Column("respondent_advocates", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column("judgments", sa.Column("advocate_text", sa.Text(), nullable=True))

    if op.get_bind().dialect.name != "postgresql":
        return
    # CONCURRENTLY cannot run inside a transaction block.
    with op.get_context().autocommit_block():
        op.execute(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {_TRGM} ON judgments "
            "USING gin (advocate_text gin_trgm_ops)"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {_TRGM}")
    for col in (
        "advocate_text", "respondent_advocates", "petitioner_advocates",
        "respondent", "petitioner", "filed_on",
    ):
        op.drop_column("judgments", col)
