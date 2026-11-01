"""Directory audience and the judicial flag on network identities.

Revision ID: 0085_identity_audience
Revises: 0084_outreach_contact_fields

Owner's decision, 1 Nov 2026: members are listed in the People directory by
default (they can opt out); judicial officers are hidden unless they choose an
audience (connections, members of their groups, their bar, or everyone). The
identity carries ``is_judicial`` and ``state`` so the cross-tenant directory
query can apply this without reading tenant-scoped profiles.

Existing identities keep their listing choice. Existing judicial officers'
identities are marked judicial and set to audience ``none`` (hidden), as the
owner asked.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0085_identity_audience"
down_revision = "0084_outreach_contact_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("network_identities", sa.Column("state", sa.String(120), nullable=True))
    op.add_column("network_identities", sa.Column("is_judicial", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("network_identities", sa.Column("audience", sa.String(20), nullable=False, server_default="everyone"))
    op.execute(
        """
        UPDATE network_identities AS i
           SET is_judicial = true, audience = 'none', discoverable = false,
               state = COALESCE(p.judicial_state, p.state)
          FROM professional_profiles AS p
         WHERE p.user_id = i.user_id AND p.deleted_at IS NULL
           AND p.professional_role = 'judicial_officer'
        """
    )
    op.execute(
        """
        UPDATE network_identities AS i
           SET state = p.state
          FROM professional_profiles AS p
         WHERE p.user_id = i.user_id AND p.deleted_at IS NULL AND i.state IS NULL AND p.state IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_column("network_identities", "audience")
    op.drop_column("network_identities", "is_judicial")
    op.drop_column("network_identities", "state")
