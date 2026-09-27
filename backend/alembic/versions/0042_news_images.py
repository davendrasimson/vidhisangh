"""Store publisher article images for visual news cards."""
from alembic import op
import sqlalchemy as sa

revision = "0042_news_images"
down_revision = "0041_knowledge_resources"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("news_items", sa.Column("image_url", sa.String(1000), nullable=True))

def downgrade() -> None:
    op.drop_column("news_items", "image_url")
