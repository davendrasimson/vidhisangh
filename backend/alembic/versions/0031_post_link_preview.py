"""Network posts: link preview (Open Graph unfurl) snapshot columns.

Revision ID: 0031_post_link_preview
Revises: 0030_webauthn
Create Date: 2026-07-19

``posts`` is a global (cross-tenant) table, so no RLS policy is involved — just
add the nullable link-preview columns.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031_post_link_preview"
down_revision: str | None = "0030_webauthn"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("link_url", sa.String(1000), nullable=True))
    op.add_column("posts", sa.Column("link_title", sa.String(500), nullable=True))
    op.add_column("posts", sa.Column("link_description", sa.Text(), nullable=True))
    op.add_column("posts", sa.Column("link_image", sa.String(1000), nullable=True))
    op.add_column("posts", sa.Column("link_site_name", sa.String(200), nullable=True))


def downgrade() -> None:
    for col in ("link_site_name", "link_image", "link_description", "link_title", "link_url"):
        op.drop_column("posts", col)
