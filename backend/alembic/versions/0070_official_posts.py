"""Official VidhiSangh feed posts: what was posted (section, judgment, news), so nothing repeats.

Global table (no RLS), like posts; written only by the daily official-posts job.

Revision ID: 0070_official_posts
Revises: 0069_hearing_court_room_item
"""

import sqlalchemy as sa

from alembic import op

revision = "0070_official_posts"
down_revision = "0069_hearing_court_room_item"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "official_posts",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("ref", sa.String(100), nullable=False),
        sa.Column("post_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("kind", "ref", name="uq_official_posts_kind_ref"),
    )


def downgrade() -> None:
    op.drop_table("official_posts")
