"""Documents and drafts: optional link to the client master.

Revision ID: 0046_document_client
Revises: 0045_matter_team_fees
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0046_document_client"
down_revision: str | None = "0045_matter_team_fees"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("documents", "drafts"):
        with op.batch_alter_table(table) as b:
            b.add_column(sa.Column("client_id", sa.Uuid(as_uuid=True), nullable=True))
            b.create_foreign_key(f"fk_{table}_client", "clients", ["client_id"], ["id"], ondelete="SET NULL")
        op.create_index(f"ix_{table}_client_id", table, ["client_id"])


def downgrade() -> None:
    for table in ("drafts", "documents"):
        op.drop_index(f"ix_{table}_client_id", table_name=table)
        with op.batch_alter_table(table) as b:
            b.drop_constraint(f"fk_{table}_client", type_="foreignkey")
            b.drop_column("client_id")
