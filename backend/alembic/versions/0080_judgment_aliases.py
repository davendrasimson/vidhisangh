"""Parallel citations: other reporters' citations for a judgment in the library.

Revision ID: 0080_judgment_aliases
Revises: 0079_neutral_citation_index

The corpus keys Supreme Court judgments by SCR and INSC citations, but practice
cites SCC and AIR. `judgment_aliases` maps "(2017) 10 SCC 1" to the record it
denotes. Rows are mined from the cross-references inside judgment texts
(``app.scripts.parallel_citations``: a citing judgment names the case and the
reporter citation; the named case is resolved in the corpus and the votes
counted) or added by curators. Global table like the rest of the research
library — no tenant_id, no RLS.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0080_judgment_aliases"
down_revision = "0079_neutral_citation_index"
branch_labels = None
depends_on = None

UUID = sa.Uuid(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "judgment_aliases",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("judgment_id", UUID, nullable=False),
        sa.Column("citation", sa.String(200), nullable=False),      # normalised, e.g. "(2017) 10 SCC 1"
        sa.Column("reporter", sa.String(40), nullable=False),       # SCC, AIR, SCALE, JT, Cri LJ …
        sa.Column("source", sa.String(20), nullable=False, server_default="mined"),
        sa.Column("support", sa.Integer(), nullable=False, server_default="1"),  # citing judgments that agree
        sa.Column("case_name_as_cited", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["judgment_id"], ["judgments.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("citation", name="uq_judgment_aliases_citation"),
    )
    op.create_index("ix_judgment_aliases_judgment_id", "judgment_aliases", ["judgment_id"])


def downgrade() -> None:
    op.drop_table("judgment_aliases")
