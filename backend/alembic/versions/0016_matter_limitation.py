"""Matter limitation date: statute-of-limitations / filing deadline for a matter.

Revision ID: 0016_limitation
Revises: 0015_calendar
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_limitation"
down_revision: str | None = "0015_calendar"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("matters", sa.Column("limitation_date", sa.Date(), nullable=True))
    op.create_index("ix_matters_limitation_date", "matters", ["limitation_date"])


def downgrade() -> None:
    op.drop_index("ix_matters_limitation_date", table_name="matters")
    op.drop_column("matters", "limitation_date")
