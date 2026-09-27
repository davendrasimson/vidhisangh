"""Profile publications: a JSON list of a practitioner's publications
(articles, papers, books) on ``professional_profiles``.

Revision ID: 0009_publications
Revises: 0008_mentions
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_publications"
down_revision: str | None = "0008_mentions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "professional_profiles",
        sa.Column("publications", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_column("professional_profiles", "publications")
