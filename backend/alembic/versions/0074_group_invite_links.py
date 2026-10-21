"""Group invite links (vidhisangh.com/join/<code>) for bar associations and law colleges.

Revision ID: 0074_group_invite_links
Revises: 0073_funnel_daily
"""

import sqlalchemy as sa

from alembic import op

revision = "0074_group_invite_links"
down_revision = "0073_funnel_daily"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("groups", sa.Column("invite_code", sa.String(16), nullable=True))
    op.create_unique_constraint("uq_groups_invite_code", "groups", ["invite_code"])


def downgrade() -> None:
    op.drop_constraint("uq_groups_invite_code", "groups", type_="unique")
    op.drop_column("groups", "invite_code")
