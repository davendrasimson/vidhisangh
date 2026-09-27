"""Access-control & audit hardening (security audit Sept 2026: A-3, A-17, A-20, A-25, P-7, P-10).

* ``audit_events`` becomes append-only: drop ``deleted_at``, add the
  ``prev_hash``/``entry_hash`` chain columns, add a trigger that rejects
  UPDATE/DELETE and revoke both from the application role (PostgreSQL only).
* ``webhook_endpoints`` gets circuit-breaker state.
* ``network_identities.discoverable`` — directory opt-in. Existing rows are
  grandfathered to ``true``; new identities default to ``false`` in the model.

Revision ID: 0048_access_control
Revises: 0047_feature_integration
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0048_access_control"
down_revision = "0047_feature_integration"
branch_labels = None
depends_on = None

# The application's database role (see app/scripts/provision_db_role.py).
APP_ROLE = "vidhisangh_app"

_IMMUTABLE_TRIGGER = """
CREATE OR REPLACE FUNCTION audit_events_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is append-only (% not allowed)', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_events_immutable ON audit_events;
CREATE TRIGGER audit_events_immutable
    BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION audit_events_immutable();
"""

_REVOKE = f"""
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
        EXECUTE 'REVOKE UPDATE, DELETE ON audit_events FROM {APP_ROLE}';
    END IF;
END
$$;
"""

_REGRANT = f"""
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
        EXECUTE 'GRANT UPDATE, DELETE ON audit_events TO {APP_ROLE}';
    END IF;
END
$$;
"""


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    # ── audit_events: append-only + hash chain ─────────────────────
    op.execute("DROP INDEX IF EXISTS ix_audit_events_deleted_at")
    with op.batch_alter_table("audit_events") as b:
        b.drop_column("deleted_at")
        b.add_column(sa.Column("prev_hash", sa.String(64), nullable=True))
        b.add_column(sa.Column("entry_hash", sa.String(64), nullable=True))
    op.create_index("ix_audit_events_prev_hash", "audit_events", ["prev_hash"])
    op.create_index("ix_audit_events_entry_hash", "audit_events", ["entry_hash"])
    if _is_postgres():
        op.execute(_IMMUTABLE_TRIGGER)
        op.execute(_REVOKE)

    # ── webhook_endpoints: circuit breaker ─────────────────────────
    with op.batch_alter_table("webhook_endpoints") as b:
        b.add_column(
            sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0")
        )
        b.add_column(sa.Column("auto_disabled_at", sa.DateTime(timezone=True), nullable=True))

    # ── network_identities: directory opt-in ───────────────────────
    with op.batch_alter_table("network_identities") as b:
        b.add_column(
            sa.Column("discoverable", sa.Boolean(), nullable=False, server_default=sa.true())
        )
    op.create_index("ix_network_identities_discoverable", "network_identities", ["discoverable"])


def downgrade() -> None:
    op.drop_index("ix_network_identities_discoverable", table_name="network_identities")
    with op.batch_alter_table("network_identities") as b:
        b.drop_column("discoverable")

    with op.batch_alter_table("webhook_endpoints") as b:
        b.drop_column("auto_disabled_at")
        b.drop_column("consecutive_failures")

    if _is_postgres():
        op.execute("DROP TRIGGER IF EXISTS audit_events_immutable ON audit_events")
        op.execute("DROP FUNCTION IF EXISTS audit_events_immutable()")
        op.execute(_REGRANT)
    op.drop_index("ix_audit_events_entry_hash", table_name="audit_events")
    op.drop_index("ix_audit_events_prev_hash", table_name="audit_events")
    with op.batch_alter_table("audit_events") as b:
        b.drop_column("entry_hash")
        b.drop_column("prev_hash")
        b.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
