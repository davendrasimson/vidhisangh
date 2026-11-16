"""Court desk: the cause lists each court published for a day, as read from the
court's public index page, and the group post that announced them.

Revision ID: 0091_court_cause_lists
Revises: 0090_whatsapp_consent_topic
"""

import sqlalchemy as sa

from alembic import op

revision = "0091_court_cause_lists"
down_revision = "0090_whatsapp_consent_topic"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "court_cause_lists",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("court_slug", sa.String(80), nullable=False),
        sa.Column("for_date", sa.Date(), nullable=False),
        sa.Column("lists", sa.JSON(), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("group_post_id", sa.Uuid()),
        sa.UniqueConstraint("court_slug", "for_date", name="uq_court_cause_list_day"),
    )
    op.create_index("ix_court_cause_lists_court_slug", "court_cause_lists", ["court_slug"])
    op.create_index("ix_court_cause_lists_for_date", "court_cause_lists", ["for_date"])


def downgrade() -> None:
    op.drop_index("ix_court_cause_lists_for_date", table_name="court_cause_lists")
    op.drop_index("ix_court_cause_lists_court_slug", table_name="court_cause_lists")
    op.drop_table("court_cause_lists")
