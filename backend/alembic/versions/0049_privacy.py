"""Privacy programme (DPDP): encrypt client identity data at rest with blind
indexes, minor/guardian fields, append-only consent events, rights requests,
terms acceptance on users, tenant offboarding columns, KYC notice/basis.

Revision ID: 0049_privacy
Revises: 0048_access_control

Data migration: existing plaintext PAN/GSTIN/TAN/CIN/Udyam/DOB/father's
name/phones are encrypted in place with the application's own crypto
(``app.core.crypto``), blind indexes are computed, KYC prefill/submission
JSON is re-written as encrypted text, submitter IPs are coarsened and the
existing consent booleans are back-filled as consent events so the ledger
starts complete. Run with the same ``VS_SECRET_KEY`` (and
``VS_BLIND_INDEX_PEPPER``, if set) as the application.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0049_privacy"
down_revision: str | None = "0048_access_control"
branch_labels = None
depends_on = None

_PREDICATE = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
)

_ENCRYPTED = ("pan", "gstin", "tan", "cin", "msme_udyam", "father_or_spouse_name", "contact_person_mobile", "mobile", "phone")


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def _pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _rls(table: str) -> None:
    if not _pg():
        return
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON {table} USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})")


def _coarse_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    try:
        addr = ipaddress.ip_address(ip.strip())
    except ValueError:
        return "invalid#" + hashlib.sha256(ip.encode()).hexdigest()[:12]
    net = ipaddress.ip_network(f"{addr}/{24 if addr.version == 4 else 48}", strict=False)
    return f"{net}#{hashlib.sha256(str(addr).encode()).hexdigest()[:12]}"


def upgrade() -> None:
    from app.core.crypto import BlindIndex, encrypt

    bind = op.get_bind()

    # ── users: terms acceptance ────────────────────────────────────
    op.add_column("users", sa.Column("terms_version", sa.String(20), nullable=True))
    op.add_column("users", sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True))

    # ── tenants: offboarding ───────────────────────────────────────
    op.add_column("tenants", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tenants", sa.Column("erase_after", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_tenants_erase_after", "tenants", ["erase_after"])

    # ── clients: widen encrypted columns, add bidx + minor/guardian ─
    for col in _ENCRYPTED:
        op.alter_column("clients", col, type_=sa.String(512), existing_nullable=True)
    if _pg():
        op.alter_column("clients", "date_of_birth", type_=sa.String(255), existing_type=sa.Date(),
                        existing_nullable=True, postgresql_using="date_of_birth::text")
    else:
        op.alter_column("clients", "date_of_birth", type_=sa.String(255), existing_nullable=True)
    op.add_column("clients", sa.Column("pan_bidx", sa.String(64), nullable=True))
    op.add_column("clients", sa.Column("gstin_bidx", sa.String(64), nullable=True))
    op.add_column("clients", sa.Column("email_bidx", sa.String(64), nullable=True))
    op.create_index("ix_clients_tenant_pan_bidx", "clients", ["tenant_id", "pan_bidx"])
    op.create_index("ix_clients_tenant_gstin_bidx", "clients", ["tenant_id", "gstin_bidx"])
    op.create_index("ix_clients_tenant_email_bidx", "clients", ["tenant_id", "email_bidx"])
    op.add_column("clients", sa.Column("is_minor", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("clients", sa.Column("guardian_name", sa.String(200), nullable=True))
    op.add_column("clients", sa.Column("guardian_relation", sa.String(60), nullable=True))
    op.add_column("clients", sa.Column("guardian_consent_recorded_at", sa.DateTime(timezone=True), nullable=True))

    # Encrypt existing plaintext in place and compute the blind indexes.
    cols = ["id", "email", "date_of_birth", *_ENCRYPTED]
    rows = bind.execute(sa.text(f"SELECT {', '.join(cols)} FROM clients")).mappings().all()
    for row in rows:
        values: dict = {"id": row["id"]}
        for col in _ENCRYPTED:
            v = row[col]
            values[col] = encrypt(str(v)) if v not in (None, "") else None
        dob = row["date_of_birth"]
        values["date_of_birth"] = encrypt(str(dob)[:10]) if dob not in (None, "") else None
        values["pan_bidx"] = BlindIndex.pan(row["pan"])
        values["gstin_bidx"] = BlindIndex.gstin(row["gstin"])
        values["email_bidx"] = BlindIndex.email(row["email"])
        sets = ", ".join(f"{c} = :{c}" for c in values if c != "id")
        bind.execute(sa.text(f"UPDATE clients SET {sets} WHERE id = :id"), values)

    # ── client_kyc_requests: encrypted JSON, coarse IP, notice, basis ─
    op.add_column("client_kyc_requests", sa.Column("lawful_basis", sa.String(20), nullable=False, server_default="contract"))
    op.add_column("client_kyc_requests", sa.Column("notice_version", sa.String(20), nullable=True))
    op.add_column("client_kyc_requests", sa.Column("prefill_enc", sa.Text(), nullable=True))
    op.add_column("client_kyc_requests", sa.Column("submitted_data_enc", sa.Text(), nullable=True))
    kyc = bind.execute(sa.text(
        "SELECT id, status, prefill, submitted_data, submitted_ip FROM client_kyc_requests"
    )).mappings().all()
    for row in kyc:
        prefill = row["prefill"]
        submitted = row["submitted_data"]
        if isinstance(prefill, str):
            prefill = json.loads(prefill) if prefill else None
        if isinstance(submitted, str):
            submitted = json.loads(submitted) if submitted else None
        # Applied requests no longer need the prefill copy (P-16).
        prefill_enc = None if row["status"] == "applied" or prefill is None else encrypt(json.dumps(prefill, default=str))
        submitted_enc = encrypt(json.dumps(submitted, default=str)) if submitted is not None else None
        bind.execute(
            sa.text("UPDATE client_kyc_requests SET prefill_enc = :p, submitted_data_enc = :s, submitted_ip = :ip WHERE id = :id"),
            {"p": prefill_enc, "s": submitted_enc, "ip": _coarse_ip(row["submitted_ip"]), "id": row["id"]},
        )
    op.drop_column("client_kyc_requests", "prefill")
    op.drop_column("client_kyc_requests", "submitted_data")
    op.alter_column("client_kyc_requests", "prefill_enc", new_column_name="prefill")
    op.alter_column("client_kyc_requests", "submitted_data_enc", new_column_name="submitted_data")

    # ── client_consent_events (append-only ledger) ─────────────────
    op.create_table(
        "client_consent_events",
        *_audit_columns(),
        sa.Column("client_id", sa.Uuid(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("purpose", sa.String(24), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(12), nullable=False),
        sa.Column("notice_version", sa.String(20), nullable=True),
        sa.Column("actor_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_coarse", sa.String(64), nullable=True),
        sa.Column("note", sa.String(300), nullable=True),
    )
    op.create_index("ix_consent_events_client_purpose", "client_consent_events", ["client_id", "purpose", "recorded_at"])
    _rls("client_consent_events")
    if _pg():
        # Append-only: the application role may insert and read, never change or remove.
        op.execute("REVOKE UPDATE, DELETE ON client_consent_events FROM PUBLIC")

    # Back-fill: today's consent flags become the first events, so the ledger
    # explains every cached flag from day one.
    now = datetime.now(UTC)
    flags = bind.execute(sa.text(
        "SELECT id, tenant_id, consent_email, consent_mobile, consent_whatsapp, consent_recorded_at, consent_source, updated_by "
        "FROM clients WHERE consent_email OR consent_mobile OR consent_whatsapp"
    )).mappings().all()
    for row in flags:
        for flag, purpose in (("consent_email", "contact_email"), ("consent_mobile", "contact_sms"), ("consent_whatsapp", "contact_whatsapp")):
            if not row[flag]:
                continue
            bind.execute(sa.text(
                "INSERT INTO client_consent_events (id, tenant_id, created_at, updated_at, client_id, purpose, granted, source, "
                "actor_id, recorded_at, note) VALUES (:id, :tid, :now, :now, :cid, :purpose, :granted, :source, :actor, :rec, :note)"
            ), {
                "id": uuid.uuid4(), "tid": row["tenant_id"], "now": now, "cid": row["id"], "purpose": purpose,
                "granted": True, "source": row["consent_source"] if row["consent_source"] in ("staff", "kyc_form") else "staff",
                "actor": row["updated_by"], "rec": row["consent_recorded_at"] or now,
                "note": "Back-filled from the consent flag at migration 0049",
            })

    # ── privacy_requests (rights register) ─────────────────────────
    op.create_table(
        "privacy_requests",
        *_audit_columns(),
        sa.Column("kind", sa.String(12), nullable=False, index=True),
        sa.Column("status", sa.String(12), nullable=False, server_default="open", index=True),
        sa.Column("source", sa.String(8), nullable=False),
        sa.Column("client_id", sa.Uuid(as_uuid=True), sa.ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("matter_id", sa.Uuid(as_uuid=True), nullable=True, index=True),
        sa.Column("subject_name", sa.String(200), nullable=True),
        sa.Column("subject_email", sa.String(320), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
    )
    _rls("privacy_requests")


def downgrade() -> None:
    """Ciphertext cannot be turned back into typed plaintext without the app
    crypto; the downgrade decrypts what it can and drops the new structures."""
    from app.core.crypto import decrypt

    bind = op.get_bind()
    if _pg():
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON privacy_requests")
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON client_consent_events")
    op.drop_table("privacy_requests")
    op.drop_index("ix_consent_events_client_purpose", table_name="client_consent_events")
    op.drop_table("client_consent_events")

    # KYC JSON back to plaintext JSON columns.
    op.add_column("client_kyc_requests", sa.Column("prefill_json", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("client_kyc_requests", sa.Column("submitted_json", sa.JSON(), nullable=True))
    for row in bind.execute(sa.text("SELECT id, prefill, submitted_data FROM client_kyc_requests")).mappings().all():
        p = json.loads(decrypt(row["prefill"])) if row["prefill"] else {}
        s = json.loads(decrypt(row["submitted_data"])) if row["submitted_data"] else None
        bind.execute(sa.text("UPDATE client_kyc_requests SET prefill_json = :p, submitted_json = :s WHERE id = :id"),
                     {"p": json.dumps(p), "s": json.dumps(s) if s is not None else None, "id": row["id"]})
    op.drop_column("client_kyc_requests", "prefill")
    op.drop_column("client_kyc_requests", "submitted_data")
    op.alter_column("client_kyc_requests", "prefill_json", new_column_name="prefill")
    op.alter_column("client_kyc_requests", "submitted_json", new_column_name="submitted_data")
    op.drop_column("client_kyc_requests", "notice_version")
    op.drop_column("client_kyc_requests", "lawful_basis")

    # Clients: decrypt in place, then narrow the types back.
    cols = ["id", "date_of_birth", *_ENCRYPTED]
    for row in bind.execute(sa.text(f"SELECT {', '.join(cols)} FROM clients")).mappings().all():
        values = {"id": row["id"]}
        for col in _ENCRYPTED + ("date_of_birth",):
            values[col] = decrypt(row[col]) if row[col] else None
        sets = ", ".join(f"{c} = :{c}" for c in values if c != "id")
        bind.execute(sa.text(f"UPDATE clients SET {sets} WHERE id = :id"), values)
    for col, length in (("pan", 10), ("gstin", 15), ("tan", 10), ("cin", 21), ("msme_udyam", 25),
                        ("father_or_spouse_name", 200), ("contact_person_mobile", 20), ("mobile", 20), ("phone", 20)):
        op.alter_column("clients", col, type_=sa.String(length), existing_nullable=True)
    if _pg():
        op.alter_column("clients", "date_of_birth", type_=sa.Date(), existing_nullable=True, postgresql_using="date_of_birth::date")
    else:
        op.alter_column("clients", "date_of_birth", type_=sa.Date(), existing_nullable=True)
    for col in ("guardian_consent_recorded_at", "guardian_relation", "guardian_name", "is_minor"):
        op.drop_column("clients", col)
    for ix in ("ix_clients_tenant_email_bidx", "ix_clients_tenant_gstin_bidx", "ix_clients_tenant_pan_bidx"):
        op.drop_index(ix, table_name="clients")
    for col in ("email_bidx", "gstin_bidx", "pan_bidx"):
        op.drop_column("clients", col)

    op.drop_index("ix_tenants_erase_after", table_name="tenants")
    op.drop_column("tenants", "erase_after")
    op.drop_column("tenants", "cancelled_at")
    op.drop_column("users", "terms_accepted_at")
    op.drop_column("users", "terms_version")
