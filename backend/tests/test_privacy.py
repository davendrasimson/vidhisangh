"""Privacy / DPDP remediation (audit A-10, P-1…P-5, P-12…P-16).

Validation errors never echo input; client identity data is encrypted at rest
with blind-index search; consent is an append-only ledger that gates sends;
minors need guardian consent; users, clients and tenants can be exported and
erased (with legal hold); rights requests are registered; retention purges are
idempotent; tokens and addresses are masked in logs.
"""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.channels import LogProvider, address_ref
from app.core.config import settings
from app.core.storage import MemoryStorage, set_storage
from app.main import app
from app.middleware.context import mask_token_path
from app.modules.clients.models import Client
from app.modules.documents.models import Document, DocumentVersion
from app.modules.drafting.models import Draft
from app.modules.identity.models import MfaBackupCode, OAuthState, RefreshToken, User, WebAuthnChallenge
from app.modules.notifications.models import Notification, NotificationChannel
from app.modules.notifications.service import send_to_client
from app.modules.privacy import retention
from app.modules.privacy.consent import coarse_ip
from app.modules.privacy.models import PrivacyRequestKind
from app.modules.privacy.router import router as privacy_router
from app.modules.privacy.service import create_rights_request
from app.modules.tenancy.models import Tenant, TenantStatus

pytestmark = pytest.mark.asyncio

API = "/api/v1"

# The privacy router is mounted by api/v1/router.py in the real app; mount it
# here too so this module is self-contained until that include lands.
if not any(getattr(r, "path", "").startswith(f"{API}/privacy") for r in app.routes):
    app.include_router(privacy_router, prefix=API)

PW = "Str0ng!Pass#2026"


async def _register(client: AsyncClient, org: str, email: str, pw: str = PW) -> tuple[dict, dict]:
    resp = await client.post(f"{API}/auth/register", json={
        "organisation_name": org, "full_name": "Adv. Owner", "email": email, "password": pw, "accept_terms": True,
    })
    assert resp.status_code == 201, resp.text
    h = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    me = (await client.get(f"{API}/auth/me", headers=h)).json()
    return h, me


# ═══ A-10 / P-2 — validation errors never echo the submitted value ═══
async def test_validation_errors_do_not_echo_input(client: AsyncClient) -> None:
    secret = "letmein12"  # weak on purpose (no upper case, no symbol)
    resp = await client.post(f"{API}/auth/register", json={
        "organisation_name": "Weak Co", "full_name": "Weak User", "email": "weak@acme.co",
        "password": secret, "accept_terms": True,
    })
    assert resp.status_code == 422
    body = resp.text
    assert secret not in body and "weak@acme.co" not in body
    for err in resp.json()["errors"]:
        assert set(err) <= {"loc", "msg", "type", "ctx"}, err
        assert "input" not in err and "url" not in err

    # Public KYC form: an over-long PAN is rejected without being echoed.
    h, _ = await _register(client, "Echo LLP", "echo@firm.co")
    c = (await client.post(f"{API}/clients", headers=h, json={"kind": "individual", "display_name": "Rahul"})).json()
    token = (await client.post(f"{API}/clients/{c['id']}/kyc", headers=h, json={})).json()["url"].rsplit("/", 1)[-1]
    bad_pan = "ABCPV1234KXYZ"
    resp = await client.post(f"{API}/kyc/{token}", json={"pan": bad_pan, "declaration_accepted": True})
    assert resp.status_code == 422 and bad_pan not in resp.text


async def test_validation_failures_log_the_field_not_the_value(client: AsyncClient) -> None:
    """Rejected sign-ups are logged by field and rule so the cause can be found,
    without what the person typed."""
    from structlog.testing import capture_logs

    secret = "Password@123"  # passes the character rules, but is on the common list
    with capture_logs() as logs:
        resp = await client.post(f"{API}/auth/register", json={
            "full_name": "Log User", "email": "log-user@acme.co", "password": secret, "accept_terms": True,
            "practice_type": "individual",
        })
    assert resp.status_code == 422
    entry = next(e for e in logs if e["event"] == "request_validation_failed")
    assert entry["fields"] == ["body.password:value_error"]
    assert secret not in json.dumps(entry) and "log-user@acme.co" not in json.dumps(entry)


# ═══ P-3 — encryption at rest + blind-index search ═══════════════════
async def test_client_identity_encrypted_at_rest_with_blind_index_search(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    h, _ = await _register(client, "Crypt LLP", "crypt@firm.co")
    created = await client.post(f"{API}/clients", headers=h, json={
        "kind": "individual", "display_name": "Sunita Verma", "first_name": "Sunita", "pan": "abcpv1234k",
        "mobile": "9876543210", "phone": "011-2345678", "date_of_birth": "1980-05-12",
        "father_or_spouse_name": "Ramesh Verma", "email": "Sunita@Example.in",
    })
    assert created.status_code == 201, created.text
    c = created.json()
    # API contract unchanged: plaintext, typed date.
    assert c["pan"] == "ABCPV1234K" and c["mobile"] == "9876543210" and c["date_of_birth"] == "1980-05-12"
    assert c["father_or_spouse_name"] == "Ramesh Verma"

    async with session_factory() as s:
        row = (await s.execute(text(
            "SELECT pan, mobile, phone, date_of_birth, father_or_spouse_name, pan_bidx, email_bidx FROM clients WHERE id = :id"
        ), {"id": c["id"].replace("-", "")})).mappings().first()
        if row is None:  # SQLite Uuid storage varies by driver; fall back to the ORM row's raw columns
            row = (await s.execute(text(
                "SELECT pan, mobile, phone, date_of_birth, father_or_spouse_name, pan_bidx, email_bidx FROM clients"
            ))).mappings().first()
    assert row is not None
    for col in ("pan", "mobile", "phone", "date_of_birth", "father_or_spouse_name"):
        assert row[col] and "gAAAA" in row[col], f"{col} stored in plaintext"  # Fernet token (with key-id prefix)
        assert "ABCPV1234K" not in row[col] and "9876543210" not in row[col] and "1980-05-12" not in row[col]
    assert row["pan_bidx"] and len(row["pan_bidx"]) == 64 and row["email_bidx"]

    # Exact-match search through the blind index (case/space-insensitive); no substring match on ciphertext.
    assert [x["id"] for x in (await client.get(f"{API}/clients", headers=h, params={"q": "abcpv 1234k"})).json()] == [c["id"]]
    assert [x["id"] for x in (await client.get(f"{API}/clients", headers=h, params={"q": "SUNITA@example.in"})).json()] == [c["id"]]
    assert (await client.get(f"{API}/clients", headers=h, params={"q": "ABCPV"})).json() == []
    # Plaintext columns still match by substring.
    assert len((await client.get(f"{API}/clients", headers=h, params={"q": "verma"})).json()) == 1

    # The KYC validators still run on decrypted values (a bad GSTIN for this PAN is flagged).
    upd = await client.patch(f"{API}/clients/{c['id']}", headers=h, json={"gstin": "07AAACR5055K1ZX"})
    assert upd.status_code == 200 and any(i["field"] == "gstin" for i in upd.json()["issues"])
    assert upd.json()["pan"] == "ABCPV1234K"


# ═══ P-5 — append-only consent ledger ════════════════════════════════
async def test_consent_ledger_is_append_only_and_drives_flags(client: AsyncClient) -> None:
    h, me = await _register(client, "Consent LLP", "consent@firm.co")
    c = (await client.post(f"{API}/clients", headers=h, json={
        "kind": "individual", "display_name": "Asha", "email": "asha@x.in", "consent_email": True,
    })).json()
    assert c["consent_email"] is True and c["consent_source"] == "staff" and c["consent_recorded_at"]
    events = (await client.get(f"{API}/clients/{c['id']}/consents", headers=h)).json()
    assert [(e["purpose"], e["granted"], e["source"]) for e in events] == [("contact_email", True, "staff")]
    assert events[0]["actor_id"] == me["id"]

    # A re-save with the same value is not a new consent.
    await client.patch(f"{API}/clients/{c['id']}", headers=h, json={"consent_email": True, "city": "Pune"})
    assert len((await client.get(f"{API}/clients/{c['id']}/consents", headers=h)).json()) == 1

    # Withdrawal: a new event; the grant stays on record; the flag follows.
    upd = (await client.patch(f"{API}/clients/{c['id']}", headers=h, json={"consent_email": False})).json()
    assert upd["consent_email"] is False
    events = (await client.get(f"{API}/clients/{c['id']}/consents", headers=h)).json()
    assert [(e["purpose"], e["granted"]) for e in events] == [("contact_email", False), ("contact_email", True)]

    # Explicit ledger entry for a non-channel purpose.
    ev = await client.post(f"{API}/clients/{c['id']}/consents", headers=h,
                           json={"purpose": "marketing", "granted": True, "note": "Ticked on the engagement letter"})
    assert ev.status_code == 201 and ev.json()["notice_version"] and ev.json()["ip_coarse"]


async def test_channel_sends_are_gated_by_consent_but_kyc_link_uses_contract_basis(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    h, _ = await _register(client, "Gate LLP", "gate@firm.co")
    c = (await client.post(f"{API}/clients", headers=h, json={
        "kind": "individual", "display_name": "Bhanu", "email": "bhanu@x.in",
    })).json()
    cid = uuid.UUID(c["id"])
    async with session_factory() as s:
        blocked = await send_to_client(s, client_id=cid, channel=NotificationChannel.EMAIL, to_email="bhanu@x.in",
                                       to_name="Bhanu", subject="Newsletter", body="…")
        assert blocked == "blocked_no_consent"
        # Contract basis (KYC link) goes through without marketing consent.
        assert await send_to_client(s, client_id=cid, channel=NotificationChannel.EMAIL, to_email="bhanu@x.in",
                                    to_name="Bhanu", subject="KYC", body="…", basis="contract") == "sent"
    await client.post(f"{API}/clients/{c['id']}/consents", headers=h, json={"purpose": "contact_email", "granted": True})
    async with session_factory() as s:
        assert await send_to_client(s, client_id=cid, channel=NotificationChannel.EMAIL, to_email="bhanu@x.in",
                                    to_name="Bhanu", subject="Newsletter", body="…") == "sent"
    # The KYC request records its basis.
    req = (await client.post(f"{API}/clients/{c['id']}/kyc", headers=h, json={})).json()
    assert req["lawful_basis"] == "contract"


async def test_kyc_form_shows_notice_and_records_version_ip_and_nulls_prefill(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    h, _ = await _register(client, "Notice LLP", "notice@firm.co")
    c = (await client.post(f"{API}/clients", headers=h, json={
        "kind": "individual", "display_name": "Chitra", "email": "chitra@x.in", "pan": "ABCPC1234K",
    })).json()
    req = (await client.post(f"{API}/clients/{c['id']}/kyc", headers=h, json={})).json()
    token = req["url"].rsplit("/", 1)[-1]
    view = (await client.get(f"{API}/kyc/{token}")).json()
    notice = view["notice"]
    assert notice["grievance_officer"]["email"] and notice["version"] and notice["purposes"] and notice["rights"]
    assert view["prefill"]["pan"] == "ABCPC1234K"

    sub = await client.post(f"{API}/kyc/{token}", headers={"x-forwarded-for": "203.0.113.77"}, json={
        "first_name": "Chitra", "consent_email": True, "consent_whatsapp": False, "consent_mobile": False,
        "declaration_accepted": True, "notice_version": notice["version"],
    })
    assert sub.status_code == 200, sub.text
    detail = (await client.get(f"{API}/clients/{c['id']}/kyc/{req['id']}", headers=h)).json()
    assert detail["notice_version"] == notice["version"] and detail["prefill"]["pan"] == "ABCPC1234K"

    applied = await client.post(f"{API}/clients/{c['id']}/kyc/{req['id']}/apply", headers=h, json={})
    assert applied.status_code == 200 and applied.json()["consent_email"] is True and applied.json()["consent_source"] == "kyc_form"
    # Prefill is nulled once applied; the submission (evidence) is kept.
    detail = (await client.get(f"{API}/clients/{c['id']}/kyc/{req['id']}", headers=h)).json()
    assert detail["prefill"] is None and detail["submitted_data"]["first_name"] == "Chitra"
    events = (await client.get(f"{API}/clients/{c['id']}/consents", headers=h)).json()
    form_events = [e for e in events if e["source"] == "kyc_form"]
    assert {e["purpose"] for e in form_events} == {"contact_email", "contact_sms", "contact_whatsapp"}
    assert all(e["notice_version"] == notice["version"] and e["ip_coarse"] == coarse_ip("203.0.113.77") for e in form_events)
    async with session_factory() as s:
        ip = (await s.execute(text("SELECT submitted_ip, prefill, submitted_data FROM client_kyc_requests"))).mappings().first()
    assert ip["submitted_ip"].startswith("203.0.113.0/24#") and "203.0.113.77" not in ip["submitted_ip"]
    assert ip["prefill"] is None and "gAAAA" in ip["submitted_data"]


# ═══ P-15 / P-16 — minors ════════════════════════════════════════════
async def test_minor_needs_guardian_consent_before_kyc(client: AsyncClient) -> None:
    h, _ = await _register(client, "Minor LLP", "minor@firm.co")
    c = (await client.post(f"{API}/clients", headers=h, json={
        "kind": "individual", "display_name": "Dev (minor)", "is_minor": True,
        "guardian_name": "Meena Rao", "guardian_relation": "mother", "email": "meena@x.in",
    })).json()
    assert c["is_minor"] is True and c["guardian_consent_recorded_at"] is None
    blocked = await client.post(f"{API}/clients/{c['id']}/kyc", headers=h, json={})
    assert blocked.status_code == 422 and "guardian" in blocked.text.lower()
    ok = await client.post(f"{API}/clients/{c['id']}/consents", headers=h, json={"purpose": "guardian_consent", "granted": True})
    assert ok.status_code == 201
    assert (await client.get(f"{API}/clients/{c['id']}", headers=h)).json()["guardian_consent_recorded_at"]
    assert (await client.post(f"{API}/clients/{c['id']}/kyc", headers=h, json={})).status_code == 201
    # The public form never lets the subject flip the minor flag.
    from app.modules.clients.schemas import KYC_FIELDS
    assert "is_minor" not in KYC_FIELDS and "guardian_name" not in KYC_FIELDS


# ═══ P-1 — client export and erasure with legal hold ═════════════════
async def test_client_export_and_erasure_respects_legal_hold(client: AsyncClient) -> None:
    h, me = await _register(client, "Erase LLP", "erase@firm.co")
    c = (await client.post(f"{API}/clients", headers=h, json={
        "kind": "individual", "display_name": "Farah Khan", "pan": "ABCPK1234F", "consent_email": True, "email": "f@x.in",
    })).json()
    m = await client.post(f"{API}/matters", headers=h, json={"title": "Khan v. State", "client_id": c["id"]})
    assert m.status_code == 201, m.text
    matter_id = m.json()["id"]

    export = await client.get(f"{API}/clients/{c['id']}/export", headers=h)
    assert export.status_code == 200 and export.headers["content-disposition"].startswith("attachment")
    bundle = export.json()
    assert bundle["client"]["pan"] == "ABCPK1234F" and "pan_bidx" not in bundle["client"]
    assert bundle["matters"][0]["id"] == matter_id and bundle["consent_events"][0]["purpose"] == "contact_email"

    # Open matter → legal hold → 409 with the holds listed.
    refused = await client.delete(f"{API}/clients/{c['id']}", headers=h, params={"erase": "true"})
    assert refused.status_code == 409, refused.text
    assert refused.json()["errors"]["legal_holds"][0]["matter_id"] == matter_id
    assert (await client.get(f"{API}/clients/{c['id']}/legal-holds", headers=h)).json()[0]["reason"] == "open"
    # Override needs a reason.
    assert (await client.delete(f"{API}/clients/{c['id']}", headers=h,
                                params={"erase": "true", "override_legal_hold": "true"})).status_code == 422
    erased = await client.delete(f"{API}/clients/{c['id']}", headers=h, params={
        "erase": "true", "override_legal_hold": "true", "reason": "Client instruction; matter withdrawn",
    })
    assert erased.status_code == 200, erased.text
    assert erased.json()["erased"] is True and erased.json()["legal_hold_overridden"] is True
    assert erased.json()["unlinked"]["matters"] == 1
    assert (await client.get(f"{API}/clients/{c['id']}", headers=h)).status_code == 404
    matter = (await client.get(f"{API}/matters/{matter_id}", headers=h)).json()
    assert matter["client_id"] is None and matter["client_name"] == "Erased client"
    audit = (await client.get(f"{API}/admin/audit", headers=h, params={"action": "client.erased"})).json()
    items = audit if isinstance(audit, list) else audit.get("items", [])
    assert items and items[0]["meta"]["legal_hold_overridden"] is True

    # Soft delete stays the default.
    c2 = (await client.post(f"{API}/clients", headers=h, json={"kind": "individual", "display_name": "Soft"})).json()
    assert (await client.delete(f"{API}/clients/{c2['id']}", headers=h)).status_code == 204
    # No matters → erasure is immediate.
    c3 = (await client.post(f"{API}/clients", headers=h, json={"kind": "individual", "display_name": "Gone"})).json()
    assert (await client.delete(f"{API}/clients/{c3['id']}", headers=h, params={"erase": "true"})).status_code == 200


# ═══ P-1 / P-4 — user export, terms acceptance, self-erasure ═════════
async def test_registration_records_terms_and_user_can_export_and_erase(
    client: AsyncClient, session_factory: async_sessionmaker
) -> None:
    h, me = await _register(client, "Self LLP", "self@firm.co")
    current_terms = str((await client.get(f"{API}/privacy/notice")).json()["terms_version"])
    assert me["terms_version"] == current_terms
    assert me["terms_accepted_at"]

    # A later policy version is accepted explicitly and recorded against the user.
    async with session_factory() as s:
        row = await s.get(User, uuid.UUID(me["id"]))
        row.terms_version = "legacy"
        await s.commit()
    assert (await client.post(f"{API}/auth/me/accept-terms", headers=h,
                              json={"accept_terms": False})).status_code == 422
    accepted = await client.post(
        f"{API}/auth/me/accept-terms", headers=h, json={"accept_terms": True}
    )
    assert accepted.status_code == 200
    assert accepted.json()["terms_version"] == current_terms
    assert accepted.json()["terms_accepted_at"]

    export = await client.get(f"{API}/privacy/me/export", headers=h)
    assert export.status_code == 200
    bundle = export.json()
    assert bundle["user"]["email"] == "self@firm.co" and "hashed_password" not in bundle["user"]
    assert bundle["sessions"] and "token_hash" not in bundle["sessions"][0]
    assert bundle["network_identity"] and bundle["network_identity"]["discoverable"] is True  # listed by default (1 Nov 2026)

    # Wrong password → 401; the only admin WITH colleagues → 409 (hand over first).
    assert (await client.post(f"{API}/privacy/me/delete", headers=h, json={"password": "Wrong!Pass#1"})).status_code == 401
    added = await client.post(f"{API}/tenants/users", headers=h, json={
        "email": "junior@firm.co", "full_name": "Junior", "role_codes": ["junior_advocate"],
    })
    assert added.status_code == 201, added.text
    assert (await client.post(f"{API}/privacy/me/delete", headers=h, json={"password": PW})).status_code == 409
    added = await client.post(f"{API}/tenants/users", headers=h, json={
        "email": "second@firm.co", "full_name": "Second Admin", "role_codes": ["org_admin"],
    })
    assert added.status_code == 201, added.text

    done = await client.post(f"{API}/privacy/me/delete", headers=h, json={"password": PW})
    assert done.status_code == 200, done.text
    assert done.json()["erased"] is True and done.json()["anonymised_email"].endswith("@anonymised.invalid")
    assert done.json()["organisation_cancelled"] is False  # colleagues keep the organisation
    assert (await client.post(f"{API}/auth/login", json={"email": "self@firm.co", "password": PW})).status_code in (401, 403)
    async with session_factory() as s:
        row = await s.scalar(select(User).where(User.id == uuid.UUID(me["id"])))
        assert row.full_name == "Deleted user" and row.email.startswith("deleted+") and row.is_active is False
        assert row.deleted_at is not None and row.mfa_enabled is False
        tokens = (await s.execute(select(RefreshToken).where(RefreshToken.user_id == row.id))).scalars().all()
        assert tokens and all(t.revoked_at is not None and t.ip_address is None for t in tokens)
        from app.modules.network.models import NetworkIdentity
        assert await s.scalar(select(NetworkIdentity).where(NetworkIdentity.user_id == row.id)) is None
        from app.modules.audit.models import AuditEvent
        assert await s.scalar(select(AuditEvent).where(AuditEvent.action == "user.erased")) is not None


async def test_solo_member_delete_cancels_organisation(client: AsyncClient, session_factory: async_sessionmaker) -> None:
    """A sign-up is a one-person organisation; its only member deletes the
    account in one step and the organisation is cancelled with it (erased by
    the retention job after the grace period). No 'make another admin first'."""
    from app.modules.tenancy.models import Tenant, TenantStatus

    h, me = await _register(client, "Solo Advocate", "solo@firm.co")
    done = await client.post(f"{API}/privacy/me/delete", headers=h, json={"password": PW})
    assert done.status_code == 200, done.text
    assert done.json()["erased"] is True and done.json()["organisation_cancelled"] is True
    assert (await client.post(f"{API}/auth/login", json={"email": "solo@firm.co", "password": PW})).status_code in (401, 403)
    async with session_factory() as s:
        row = await s.scalar(select(User).where(User.id == uuid.UUID(me["id"])))
        assert row.is_active is False and row.deleted_at is not None
        tenant = await s.get(Tenant, row.tenant_id)
        assert tenant.status == TenantStatus.CANCELLED and tenant.cancelled_at is not None
        assert tenant.erase_after is not None and tenant.erase_after > tenant.cancelled_at
        from app.modules.audit.models import AuditEvent
        assert await s.scalar(select(AuditEvent).where(
            AuditEvent.action == "tenant.cancelled", AuditEvent.tenant_id == tenant.id)) is not None


# ═══ P-1 (g) — rights requests ═══════════════════════════════════════
async def test_rights_requests_register(client: AsyncClient, session_factory: async_sessionmaker) -> None:
    h, me = await _register(client, "Rights LLP", "rights@firm.co")
    c = (await client.post(f"{API}/clients", headers=h, json={"kind": "individual", "display_name": "Gita"})).json()
    created = await client.post(f"{API}/privacy/requests", headers=h, json={
        "kind": "correction", "message": "My address has changed.", "client_id": c["id"],
    })
    assert created.status_code == 201, created.text
    r = created.json()
    assert r["status"] == "open" and r["source"] == "staff" and r["due_at"] and r["created_by"] == me["id"]
    listed = (await client.get(f"{API}/privacy/requests", headers=h, params={"status": "open"})).json()
    assert [x["id"] for x in listed] == [r["id"]]
    upd = await client.patch(f"{API}/privacy/requests/{r['id']}", headers=h,
                             json={"status": "resolved", "resolution_note": "Address updated on the record."})
    assert upd.status_code == 200 and upd.json()["resolved_at"] and upd.json()["resolved_by"] == me["id"]

    # The portal calls the service directly with the resolved access.
    class _Access:  # what PortalAccess exposes
        tenant_id = uuid.UUID(me["tenant_id"])
        matter_id = uuid.uuid4()
        client_name = "Gita"
        client_email = "gita@x.in"

    async with session_factory() as s:
        req = await create_rights_request(s, _Access(), PrivacyRequestKind.GRIEVANCE, "I was not told about the fee.")
        await s.commit()
    got = (await client.get(f"{API}/privacy/requests/{req.id}", headers=h)).json()
    assert got["source"] == "portal" and got["kind"] == "grievance" and got["subject_email"] == "gita@x.in"
    # Tenant isolation.
    other, _ = await _register(client, "Other LLP", "other@firm.co")
    assert (await client.get(f"{API}/privacy/requests/{req.id}", headers=other)).status_code == 404


# ═══ P-13 — tenant privacy settings, export, cancellation ════════════
async def test_tenant_privacy_settings_export_and_cancellation(client: AsyncClient, session_factory: async_sessionmaker) -> None:
    h, me = await _register(client, "Offboard LLP", "off@firm.co")
    await client.post(f"{API}/clients", headers=h, json={"kind": "individual", "display_name": "Hina", "pan": "ABCPH1234K"})

    ps = (await client.get(f"{API}/tenants/current/privacy", headers=h)).json()
    assert ps["matter_retention_years"] == 8 and ps["sub_processors"]
    upd = await client.patch(f"{API}/tenants/current/privacy", headers=h,
                             json={"data_protection_contact_email": "dpo@offboard.in", "matter_retention_years": 10})
    assert upd.status_code == 200 and upd.json()["matter_retention_years"] == 10
    assert (await client.get(f"{API}/tenants/current/privacy", headers=h)).json()["data_protection_contact_email"] == "dpo@offboard.in"

    export = await client.post(f"{API}/tenants/current/export", headers=h)
    assert export.status_code == 200 and export.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(export.content))
    names = set(zf.namelist())
    assert {"tenant.json", "manifest.json", "clients.json", "users.json", "audit_events.json"} <= names
    clients_json = json.loads(zf.read("clients.json"))
    assert clients_json[0]["pan"] == "ABCPH1234K" and "pan_bidx" not in clients_json[0]
    users_json = json.loads(zf.read("users.json"))
    assert "hashed_password" not in users_json[0]

    slug = (await client.get(f"{API}/tenants/current", headers=h)).json()["slug"]
    assert (await client.request("DELETE", f"{API}/tenants/current", headers=h,
                                 json={"confirm_slug": "wrong", "password": PW})).status_code == 422
    assert (await client.request("DELETE", f"{API}/tenants/current", headers=h,
                                 json={"confirm_slug": slug, "password": "Nope!Pass#1"})).status_code == 401
    done = await client.request("DELETE", f"{API}/tenants/current", headers=h, json={"confirm_slug": slug, "password": PW})
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["status"] == "cancelled" and body["users_disabled"] == 1
    erase_after = datetime.fromisoformat(body["erase_after"])
    assert erase_after - datetime.fromisoformat(body["cancelled_at"]) >= timedelta(days=29)
    assert (await client.post(f"{API}/auth/login", json={"email": "off@firm.co", "password": PW})).status_code in (401, 403)

    # The purge erases the tenant once the grace period has passed.
    set_storage(MemoryStorage())
    async with session_factory() as s:
        tenant = await s.scalar(select(Tenant).where(Tenant.id == uuid.UUID(me["tenant_id"])))
        assert tenant.status == TenantStatus.CANCELLED
        assert await retention.purge_cancelled_tenants(s) == 0  # not yet due
        tenant.erase_after = datetime.now(UTC) - timedelta(days=1)
        await s.commit()
    async with session_factory() as s:
        assert await retention.purge_cancelled_tenants(s) == 1
        await s.commit()
    async with session_factory() as s:
        assert await s.scalar(select(Tenant).where(Tenant.id == uuid.UUID(me["tenant_id"]))) is None
        assert (await s.execute(select(Client).where(Client.tenant_id == uuid.UUID(me["tenant_id"])))).scalars().all() == []
        assert (await s.execute(select(User).where(User.tenant_id == uuid.UUID(me["tenant_id"])))).scalars().all() == []
        assert await retention.purge_cancelled_tenants(s) == 0  # idempotent
    set_storage(None)


# ═══ P-14 — retention purges ═════════════════════════════════════════
async def test_retention_purges_are_idempotent(client: AsyncClient, session_factory: async_sessionmaker) -> None:
    h, me = await _register(client, "Purge LLP", "purge@firm.co")
    tid, uid = uuid.UUID(me["tenant_id"]), uuid.UUID(me["id"])
    old = datetime.now(UTC) - timedelta(days=40)
    store = MemoryStorage()
    set_storage(store)
    try:
        await store.put("t/doc-old", b"bytes", "text/plain")
        await store.put("t/doc-live", b"bytes", "text/plain")
        async with session_factory() as s:
            s.add(OAuthState(state="s1", provider="google", code_verifier="v", redirect_uri="https://x", nonce="n",
                             expires_at=old))
            s.add(OAuthState(state="s2", provider="google", code_verifier="v", redirect_uri="https://x", nonce="n",
                             expires_at=datetime.now(UTC) + timedelta(hours=1)))
            s.add(WebAuthnChallenge(challenge="c1", kind="authentication", expires_at=old))
            s.add(RefreshToken(tenant_id=tid, user_id=uid, token_hash="h-old", expires_at=old + timedelta(days=14),
                               revoked_at=old, ip_address="1.2.3.4", user_agent="UA"))
            s.add(RefreshToken(tenant_id=tid, user_id=uid, token_hash="h-recent", expires_at=datetime.now(UTC) + timedelta(days=7),
                               revoked_at=datetime.now(UTC), ip_address="1.2.3.4", user_agent="UA"))
            s.add(MfaBackupCode(tenant_id=tid, user_id=uid, code_hash="used", used_at=old))
            s.add(MfaBackupCode(tenant_id=tid, user_id=uid, code_hash="fresh"))
            s.add(Notification(user_id=uid, type="mention", message="old", created_at=old - timedelta(days=400)))
            s.add(Notification(user_id=uid, type="mention", message="new"))
            for name, key, deleted in (("old.txt", "t/doc-old", old), ("live.txt", "t/doc-live", None)):
                doc = Document(tenant_id=tid, name=name, content_type="text/plain", size=5, uploaded_by=uid, deleted_at=deleted)
                s.add(doc)
                await s.flush()
                s.add(DocumentVersion(tenant_id=tid, document_id=doc.id, version_no=1, storage_key=key, size=5,
                                      content_type="text/plain", checksum="x", uploaded_by=uid))
            s.add(Draft(tenant_id=tid, title="old draft", created_by=uid, updated_by=uid, deleted_at=old))
            s.add(Draft(tenant_id=tid, title="live draft", created_by=uid, updated_by=uid))
            await s.commit()

        async with session_factory() as s:
            counts = {fn.__name__: await fn(s) for fn in retention.PRIVACY_PURGES}
            await s.commit()
        assert counts["purge_oauth_states"] == 1 and counts["purge_webauthn_challenges"] == 1
        assert counts["purge_refresh_tokens"] == 1 and counts["purge_used_backup_codes"] == 1
        assert counts["purge_deleted_documents"] == 1 and counts["purge_deleted_drafts"] == 1
        assert counts["purge_notifications"] == 1 and counts["purge_cancelled_tenants"] == 0
        assert "t/doc-old" not in store._store and "t/doc-live" in store._store

        async with session_factory() as s:
            recent = await s.scalar(select(RefreshToken).where(RefreshToken.token_hash == "h-recent"))
            assert recent is not None and recent.ip_address is None and recent.user_agent is None
            assert await s.scalar(select(OAuthState).where(OAuthState.state == "s2")) is not None
            assert (await s.execute(select(Draft))).scalars().one().title == "live draft"
            # Second run: nothing left to do.
            again = {fn.__name__: await fn(s) for fn in retention.PRIVACY_PURGES}
            await s.commit()
        assert set(again.values()) == {0}
    finally:
        set_storage(None)


# ═══ P-12 — log masking ══════════════════════════════════════════════
async def test_tokens_and_addresses_are_masked_in_logs() -> None:
    assert mask_token_path("/api/v1/kyc/abcDEF123-_xyz") == "/api/v1/kyc/<token>"
    assert mask_token_path("/api/v1/portal/client/tok123/documents/9") == "/api/v1/portal/client/<token>/documents/9"
    assert mask_token_path("/api/v1/portal/tok123") == "/api/v1/portal/<token>"
    assert mask_token_path("/api/v1/clients/123") == "/api/v1/clients/123"
    ref = address_ref("Someone@Example.in")
    assert len(ref) == 12 and "example" not in ref and ref == address_ref("someone@example.in")
    assert coarse_ip("203.0.113.77") == coarse_ip("203.0.113.78").split("#")[0] + "#" + coarse_ip("203.0.113.77").split("#")[1]
    assert coarse_ip("203.0.113.77").startswith("203.0.113.0/24#") and coarse_ip(None) is None

    import logging

    records: list[logging.LogRecord] = []

    class _Catch(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger("vidhisangh.notifications")
    handler = _Catch()
    logger.addHandler(handler)
    level = logger.level
    logger.setLevel(logging.INFO)
    try:
        from app.core.channels import ChannelMessage
        await LogProvider().send(ChannelMessage(to_email="victim@example.in", to_name="Victim", subject="Hi", body="secret body"))
    finally:
        logger.removeHandler(handler)
        logger.setLevel(level)
    rendered = " ".join(r.getMessage() for r in records)
    assert "notify[log]" in rendered and "victim@example.in" not in rendered and "secret body" not in rendered


async def test_public_notice_and_settings_defaults(client: AsyncClient) -> None:
    resp = await client.get(f"{API}/privacy/notice")
    assert resp.status_code == 200
    n = resp.json()
    assert n["grievance_officer"]["name"] and n["notice_url"].endswith("/privacy") and n["terms_url"].endswith("/terms")
    assert n["legal_hold_years"] == 8 and n["tenant_erase_grace_days"] == 30 and n["retention_days"]["notifications"] == 365
    assert any(p["name"].startswith("Razorpay") for p in n["sub_processors"])
    assert settings.PUBLIC_APP_URL.rstrip("/") in n["notice_url"]
