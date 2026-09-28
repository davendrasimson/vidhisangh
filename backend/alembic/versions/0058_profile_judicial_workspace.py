"""Detailed profiles, privacy groups and judicial office fields.

Revision ID: 0058_profile_judicial_workspace
Revises: 0057_network_moderation
"""

from __future__ import annotations

import json

import sqlalchemy as sa

from alembic import op

revision: str = "0058_profile_judicial_workspace"
down_revision: str | None = "0057_network_moderation"
branch_labels = None
depends_on = None

DEFAULTS = json.dumps(
    {
        "about": "everyone",
        "professional": "everyone",
        "education": "connections",
        "location": "connections",
        "contact": "none",
        "judicial": "connections",
    }
)


def upgrade() -> None:
    columns = [
        sa.Column("professional_role", sa.String(80), nullable=True),
        sa.Column("designation", sa.String(160), nullable=True),
        sa.Column("employment_history", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("memberships", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("professional_email", sa.String(320), nullable=True),
        sa.Column("professional_phone", sa.String(30), nullable=True),
        sa.Column("postal_code", sa.String(12), nullable=True),
        sa.Column("judicial_court_name", sa.String(250), nullable=True),
        sa.Column("judicial_court_address", sa.String(400), nullable=True),
        sa.Column("judicial_district", sa.String(120), nullable=True),
        sa.Column("judicial_state", sa.String(120), nullable=True),
        sa.Column("visibility_settings", sa.JSON(), nullable=False, server_default=DEFAULTS),
    ]
    for column in columns:
        op.add_column("professional_profiles", column)
    op.create_index(
        "ix_professional_profiles_professional_role", "professional_profiles", ["professional_role"]
    )


def downgrade() -> None:
    op.drop_index("ix_professional_profiles_professional_role", table_name="professional_profiles")
    for name in [
        "visibility_settings",
        "judicial_state",
        "judicial_district",
        "judicial_court_address",
        "judicial_court_name",
        "postal_code",
        "professional_phone",
        "professional_email",
        "memberships",
        "employment_history",
        "designation",
        "professional_role",
    ]:
        op.drop_column("professional_profiles", name)
