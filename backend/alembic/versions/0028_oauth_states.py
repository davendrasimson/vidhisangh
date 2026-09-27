"""OAuth/OIDC sign-in state (global, pre-authentication — no tenant, no RLS).

Revision ID: 0028_oauth_states
Revises: 0027_webhooks
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_oauth_states"
down_revision: str | None = "0027_webhooks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = sa.Uuid(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "oauth_states",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("state", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("code_verifier", sa.String(128), nullable=False),
        sa.Column("redirect_uri", sa.String(500), nullable=False),
        sa.Column("login_hint", sa.String(320), nullable=True),
        sa.Column("nonce", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("state", name="uq_oauth_states_state"),
    )
    op.create_index("ix_oauth_states_state", "oauth_states", ["state"])


def downgrade() -> None:
    op.drop_table("oauth_states")
