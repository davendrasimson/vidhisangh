"""Messaging module: conversations (direct/group), participants and messages.

Global cross-tenant chat layer — no tenant_id scoping, no RLS. Direct chats are
deduplicated via a unique canonical ``direct_key``.

Revision ID: 0010_messaging
Revises: 0009_publications
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_messaging"
down_revision: str | None = "0009_publications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = sa.Uuid(as_uuid=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("type", sa.String(20), nullable=False, server_default="direct"),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("created_by", UUID, nullable=False),
        sa.Column("direct_key", sa.String(120), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_preview", sa.String(200), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("direct_key", name="conversation_direct_key"),
    )
    op.create_index("ix_conversations_created_by", "conversations", ["created_by"])
    op.create_index("ix_conversations_last_message_at", "conversations", ["last_message_at"])

    op.create_table(
        "conversation_participants",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("conversation_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("participant_name", sa.String(200), nullable=False),
        sa.Column("participant_avatar_url", sa.String(500), nullable=True),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("conversation_id", "user_id", name="participant_unique"),
    )
    op.create_index(
        "ix_conversation_participants_conversation_id",
        "conversation_participants",
        ["conversation_id"],
    )
    op.create_index(
        "ix_conversation_participants_user_id", "conversation_participants", ["user_id"]
    )

    op.create_table(
        "messages",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("conversation_id", UUID, nullable=False),
        sa.Column("sender_id", UUID, nullable=False),
        sa.Column("sender_name", sa.String(200), nullable=False),
        sa.Column("sender_avatar_url", sa.String(500), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index("ix_messages_sender_id", "messages", ["sender_id"])


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_table("conversation_participants")
    op.drop_table("conversations")
