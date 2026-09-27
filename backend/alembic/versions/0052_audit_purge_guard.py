"""Audit log stays append-only, but a tenant erasure (DPDP s.8(7), P-13) must be
able to cascade through it: the trigger now allows DELETE only inside a
transaction that has set ``app.audit_purge = 'on'`` (the retention purge does),
and never allows UPDATE.

Revision ID: 0052_audit_purge_guard
Revises: 0051_lawful_basis
"""

from __future__ import annotations

from alembic import op

revision: str = "0052_audit_purge_guard"
down_revision: str | None = "0051_lawful_basis"
branch_labels = None
depends_on = None

_GUARDED = """
CREATE OR REPLACE FUNCTION audit_events_immutable() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_setting('app.audit_purge', true) = 'on' THEN
        RETURN OLD;  -- sanctioned erasure (tenant offboarding / retention purge)
    END IF;
    RAISE EXCEPTION 'audit_events is append-only (% not allowed)', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;
"""

_STRICT = """
CREATE OR REPLACE FUNCTION audit_events_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is append-only (% not allowed)', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(_GUARDED)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(_STRICT)
