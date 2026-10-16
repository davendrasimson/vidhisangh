"""Feed posts: formatted text and photos.

``posts.content_html`` holds allow-listed HTML (``content`` keeps the plain
text). ``post_images`` is a global table like the other network tables (no
RLS): an image belongs to its uploader until a post is published with it.

Revision ID: 0066_post_rich_text_images
Revises: 0065_referrals
"""

import sqlalchemy as sa

from alembic import op

revision = "0066_post_rich_text_images"
down_revision = "0065_referrals"
branch_labels = None
depends_on = None

UUID = sa.Uuid(as_uuid=True)


def upgrade() -> None:
    op.add_column("posts", sa.Column("content_html", sa.Text(), nullable=True))
    op.create_table(
        "post_images",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("uploader_id", UUID, nullable=False),
        sa.Column("post_id", UUID, sa.ForeignKey("posts.id", ondelete="CASCADE"), nullable=True),
        sa.Column("storage_key", sa.String(300), nullable=False),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_post_images_uploader_id", "post_images", ["uploader_id"])
    op.create_index("ix_post_images_post_id", "post_images", ["post_id"])


def downgrade() -> None:
    op.drop_table("post_images")
    op.drop_column("posts", "content_html")
