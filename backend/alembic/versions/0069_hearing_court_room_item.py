"""Hearings: courtroom and cause-list item number (for the diary and WhatsApp reminders).

Revision ID: 0069_hearing_court_room_item
Revises: 0068_hearing_reminders
"""

import sqlalchemy as sa

from alembic import op

revision = "0069_hearing_court_room_item"
down_revision = "0068_hearing_reminders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hearings", sa.Column("court_room", sa.String(40), nullable=True))
    op.add_column("hearings", sa.Column("item_number", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("hearings", "item_number")
    op.drop_column("hearings", "court_room")
