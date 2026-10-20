"""Public profile pages (vidhisangh.com/in/<handle>/): a separate opt-in on the network identity.

Revision ID: 0071_public_profile_pages
Revises: 0070_official_posts
"""

import sqlalchemy as sa

from alembic import op

revision = "0071_public_profile_pages"
down_revision = "0070_official_posts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("network_identities", sa.Column("public_page", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("network_identities", sa.Column("public_handle", sa.String(60), nullable=True))
    op.add_column("network_identities", sa.Column("public_page_consented_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_network_identities_public_page", "network_identities", ["public_page"])
    op.create_unique_constraint("uq_network_identities_public_handle", "network_identities", ["public_handle"])


def downgrade() -> None:
    op.drop_constraint("uq_network_identities_public_handle", "network_identities", type_="unique")
    op.drop_index("ix_network_identities_public_page", table_name="network_identities")
    op.drop_column("network_identities", "public_page_consented_at")
    op.drop_column("network_identities", "public_handle")
    op.drop_column("network_identities", "public_page")
