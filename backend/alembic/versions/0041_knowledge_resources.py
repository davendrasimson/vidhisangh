"""Knowledge source links, review dates and document references."""
import sqlalchemy as sa
from alembic import op

revision = "0041_knowledge_resources"
down_revision = "0040_research_full_text"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_items", sa.Column("source_url", sa.String(2000), nullable=True))
    op.add_column("knowledge_items", sa.Column("reviewed_on", sa.Date(), nullable=True))
    op.add_column("knowledge_items", sa.Column("attachments", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))


def downgrade() -> None:
    op.drop_column("knowledge_items", "attachments")
    op.drop_column("knowledge_items", "reviewed_on")
    op.drop_column("knowledge_items", "source_url")
