"""Users: make the email address unique across ALL tenants.

Revision ID: 0032_users_email_global_unique
Revises: 0031_post_link_preview
Create Date: 2026-09-08

Previously ``users`` was unique on ``(tenant_id, email)``, so one address could
belong to several organisations. Sign-in then could not tell them apart and
failed with "Multiple organisations match this email — specify tenant_slug".
An address now identifies exactly one account platform-wide.

The index is partial (``deleted_at IS NULL``), matching the filter every user
lookup already applies, so a soft-deleted account does not hold its address
against the whole platform. It is built on ``lower(email)``: the app lowercases
on write, and this stops a differently-cased duplicate from slipping in.

The per-tenant ``users_tenant_email`` constraint is intentionally kept — leaving
it in place keeps the downgrade path exact and costs only one small index. Note
it is NOT partial, which is why a soft-deleted address can be re-used by a
*different* organisation but not by the one that soft-deleted it. That predates
this migration and is unchanged by it.

**This migration fails if duplicates already exist** — that is deliberate, since
silently picking a winner would delete somebody's access. Resolve them first:

    SELECT lower(email), count(*) FROM users WHERE deleted_at IS NULL
    GROUP BY 1 HAVING count(*) > 1;
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032_users_email_global_unique"
down_revision: str | None = "0031_post_link_preview"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    duplicates = conn.execute(
        sa.text(
            "SELECT lower(email) AS email, count(*) AS n FROM users "
            "WHERE deleted_at IS NULL GROUP BY lower(email) HAVING count(*) > 1 "
            "ORDER BY n DESC, email"
        )
    ).all()
    if duplicates:
        listed = ", ".join(f"{row.email} ({row.n})" for row in duplicates[:10])
        more = "" if len(duplicates) <= 10 else f" and {len(duplicates) - 10} more"
        raise RuntimeError(
            "Cannot make user emails globally unique — these addresses are used by "
            f"more than one active account: {listed}{more}. Merge, soft-delete or "
            "re-address the extras, then run this migration again."
        )

    op.create_index(
        "users_email_global_unique",
        "users",
        [sa.text("lower(email)")],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("users_email_global_unique", table_name="users")
