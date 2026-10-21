"""Group posts: formatted text and photos, like feed posts.

Revision ID: 0075_group_post_rich
Revises: 0074_group_invite_links
"""

import sqlalchemy as sa

from alembic import op

revision = "0075_group_post_rich"
down_revision = "0074_group_invite_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("group_posts", sa.Column("content_html", sa.Text(), nullable=True))
    op.add_column("post_images", sa.Column("group_post_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_post_images_group_post", "post_images", "group_posts", ["group_post_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_post_images_group_post_id", "post_images", ["group_post_id"])


def downgrade() -> None:
    op.drop_index("ix_post_images_group_post_id", table_name="post_images")
    op.drop_constraint("fk_post_images_group_post", "post_images", type_="foreignkey")
    op.drop_column("post_images", "group_post_id")
    op.drop_column("group_posts", "content_html")
