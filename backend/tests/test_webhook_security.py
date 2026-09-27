"""Security audit (Sept 2026) — webhooks & audit trail.

A-3  webhook SSRF: URL guard at create/update/delivery, pinned IP, no redirects,
     no response body stored.
A-25 ``t=…,v1=…`` signatures with a 5-minute window; queued delivery with
     retries; per-endpoint circuit breaker.
A-20 append-only audit log with a hash chain; ``security.*`` events.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app.core.link_preview import set_http_client_factory
from app.core.webhook_transport import HttpxTransport, RecordingTransport
from app.modules.audit.models import AuditEvent
from app.modules.audit.service import GENESIS_HASH, verify_chain
from app.modules.webhooks.models import AUTO_DISABLE_AFTER_FAILURES, WebhookEndpoint
from app.modules.webhooks.service import (
    dispatcher,
    emit_security_event,
    sign_payload,
    verify_signature,
)
from tests.conftest import FAKE_DNS, PUBLIC_IP

pytestmark = pytest.mark.asyncio

API = "/api/v1"


async def _user(client: AsyncClient, org: str, email: str, pw: str) -> tuple[dict, dict]:
    resp = await client.post(
        f"{API}/auth/register",
        json={
            "organisation_name": org,
            "full_name": f"Adv. {email.split('@')[0].title()}",
            "email": email,
            "password": pw,
            "accept_terms": True,
        },
    )
    assert resp.status_code == 201, resp.text
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    me = (await client.get(f"{API}/auth/me", headers=headers)).json()
    return headers, me


async def _hook(client: AsyncClient, h: dict, url: str, events: list[str] | None = None) -> dict:
    resp = await client.post(f"{API}/webhooks", headers=h, json={"url": url, "event_types": events or ["ping"]})
    assert resp.status_code == 201, resp.text
    return resp.json()


# ─── A-3: SSRF guard ────────────────────────────────────────────────
@pytest.mark.parametrize(
    "url",
    [
        "https://private.test/hook",       # RFC1918
        "https://loopback.test/hook",      # 127.0.0.1
        "https://linklocal.test/hook",     # 169.254/16
        "https://metadata.test/hook",      # cloud metadata address
        "https://v6loopback.test/hook",    # ::1
        "https://mixed.test/hook",         # one private A record among public ones
        "https://unresolvable.test/hook",  # no address at all
        "https://169.254.169.254/latest/meta-data",
        "https://127.0.0.1:8000/admin",
        "https://[::1]/hook",
        "https://10.0.0.1/hook",
        "https://metadata.google.internal/computeMetadata/v1/",
        "ftp://example.com/hook",
    ],
)
async def test_webhook_rejects_internal_targets(client: AsyncClient, strong_password: str, url: str) -> None:
    h, _ = await _user(client, "SSRF LLP", f"u{abs(hash(url)) % 10**6}@ssrf.co", strong_password)
    resp = await client.post(f"{API}/webhooks", headers=h, json={"url": url, "event_types": ["ping"]})
    assert resp.status_code == 422, resp.text
    assert (await client.get(f"{API}/webhooks", headers=h)).json() == []


async def test_webhook_update_revalidates_url_and_delivery_rechecks_dns(
    client: AsyncClient, strong_password: str, webhook_transport: RecordingTransport
) -> None:
    h, _ = await _user(client, "Rebind LLP", "u@rebind.co", strong_password)
    hook = await _hook(client, h, "https://rebind.test/hook")

    # PATCHing the URL to something internal is refused.
    bad = await client.patch(f"{API}/webhooks/{hook['id']}", headers=h, json={"url": "https://private.test/x"})
    assert bad.status_code == 422
    assert (await client.get(f"{API}/webhooks", headers=h)).json()[0]["url"] == "https://rebind.test/hook"

    # DNS rebinding: the name was public at registration and now points inside.
    FAKE_DNS["rebind.test"] = ["10.0.0.9"]
    try:
        test = await client.post(f"{API}/webhooks/{hook['id']}/test", headers=h)
        assert test.status_code == 200
        body = test.json()
        assert body["status"] == "failed" and body["status_code"] is None
        assert body["detail"] == "failed: UnsafeUrlError"
        assert webhook_transport.calls == []  # never reached the transport
    finally:
        FAKE_DNS.pop("rebind.test", None)


async def test_deliveries_never_expose_response_body(
    client: AsyncClient, strong_password: str, webhook_transport: RecordingTransport
) -> None:
    h, _ = await _user(client, "Body LLP", "u@body.co", strong_password)
    hook = await _hook(client, h, "https://receiver.test/hook")
    webhook_transport.status_code = 500
    test = await client.post(f"{API}/webhooks/{hook['id']}/test", headers=h)
    assert test.json()["status"] == "failed" and test.json()["status_code"] == 500
    assert test.json()["detail"] == "failed: non-2xx response"
    webhook_transport.status_code = 200
    ok = await client.post(f"{API}/webhooks/{hook['id']}/test", headers=h)
    assert ok.json()["detail"] == "delivered"
    for d in (await client.get(f"{API}/webhooks/{hook['id']}/deliveries", headers=h)).json():
        assert d["detail"] in ("delivered", "failed: non-2xx response")


async def test_httpx_transport_pins_ip_and_never_follows_redirects(client: AsyncClient) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        # A redirect to an internal address must NOT be followed.
        return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"}, text="secret body")

    set_http_client_factory(lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kw))
    try:
        status, reason = await HttpxTransport().send("https://receiver.test:8443/hook", {"X": "1"}, b"{}")
    finally:
        set_http_client_factory(None)
    assert status == 302 and reason == ""  # not followed; body not returned
    assert len(seen) == 1
    req = seen[0]
    assert req.url.host == PUBLIC_IP and req.url.port == 8443  # connected to the vetted IP…
    assert req.headers["host"] == "receiver.test:8443"  # …with the original Host
    assert req.extensions.get("sni_hostname") == "receiver.test"  # …and TLS name


# ─── A-25: signatures, queue, retries, breaker ──────────────────────
async def test_signature_scheme_and_replay_window() -> None:
    body = b'{"event":"ping"}'
    header = f"t=1000,v1={sign_payload('whsec_x', 1000, body)}"
    assert verify_signature("whsec_x", header, body, now=1000 + 299)
    assert not verify_signature("whsec_x", header, body, now=1000 + 301)  # replayed too late
    assert not verify_signature("whsec_x", header, body + b" ", now=1000)  # body tampered
    assert not verify_signature("other", header, body, now=1000)
    assert not verify_signature("whsec_x", "garbage", body, now=1000)


async def test_failed_deliveries_retry_then_succeed(
    client: AsyncClient, strong_password: str, webhook_transport: RecordingTransport
) -> None:
    h, _ = await _user(client, "Retry LLP", "u@retry.co", strong_password)
    hook = await _hook(client, h, "https://receiver.test/hook", ["matter.created"])
    webhook_transport.fail_times = 2
    created = await client.post(f"{API}/matters", headers=h, json={"title": "Matter", "client_name": "C"})
    assert created.status_code == 201, created.text
    assert dispatcher.pending == 1
    await dispatcher.drain()
    deliveries = (await client.get(f"{API}/webhooks/{hook['id']}/deliveries", headers=h)).json()
    statuses = sorted(d["status"] for d in deliveries)
    assert statuses == ["failed", "failed", "success"]
    assert any(d["detail"] == "delivered (attempt 3/3)" for d in deliveries)
    ep = (await client.get(f"{API}/webhooks", headers=h)).json()[0]
    assert ep["is_active"] is True and ep["consecutive_failures"] == 0  # success closes the breaker


async def test_circuit_breaker_disables_endpoint_after_consecutive_failures(
    client: AsyncClient, strong_password: str, webhook_transport: RecordingTransport
) -> None:
    h, _ = await _user(client, "Breaker LLP", "u@breaker.co", strong_password)
    hook = await _hook(client, h, "https://dead.test/hook", ["matter.created"])
    webhook_transport.status_code = 503
    # Two events × 3 attempts = 6 failures ≥ threshold (5).
    for i in range(2):
        await client.post(f"{API}/matters", headers=h, json={"title": f"Matter {i}", "client_name": "C"})
    await dispatcher.drain()
    ep = (await client.get(f"{API}/webhooks", headers=h)).json()[0]
    assert ep["is_active"] is False and ep["auto_disabled_at"] is not None
    assert ep["consecutive_failures"] == AUTO_DISABLE_AFTER_FAILURES
    deliveries = (await client.get(f"{API}/webhooks/{hook['id']}/deliveries", headers=h)).json()
    assert len(deliveries) == AUTO_DISABLE_AFTER_FAILURES  # stopped as soon as it tripped
    audit = (await client.get(f"{API}/admin/audit", headers=h, params={"action": "webhook.auto_disabled"})).json()
    assert len(audit) == 1 and audit[0]["entity_id"] == hook["id"]
    # Re-enabling by hand resets the breaker.
    webhook_transport.status_code = 200
    re = await client.patch(f"{API}/webhooks/{hook['id']}", headers=h, json={"is_active": True})
    assert re.json()["is_active"] is True and re.json()["consecutive_failures"] == 0
    assert re.json()["auto_disabled_at"] is None


# ─── A-20: audit log ────────────────────────────────────────────────
async def test_audit_event_has_no_soft_delete() -> None:
    assert not hasattr(AuditEvent, "deleted_at")
    assert "deleted_at" not in AuditEvent.__table__.c


async def test_audit_chain_verifies_and_detects_tampering(
    client: AsyncClient, strong_password: str, session_factory
) -> None:
    h, me = await _user(client, "Chain LLP", "u@chain.co", strong_password)
    await _hook(client, h, "https://a.test/1")  # webhook.created
    await _hook(client, h, "https://a.test/2")  # webhook.created (same tenant → chained)
    await client.put(f"{API}/admin/feature-flags/legal_news", headers=h, json={"enabled": False})

    events = (await client.get(f"{API}/admin/audit", headers=h)).json()
    assert len(events) >= 3 and all(e["entry_hash"] for e in events)
    assert (await client.get(f"{API}/admin/audit/verify", headers=h)).json() == {"ok": True, "first_broken_id": None}

    tenant_id = uuid.UUID(me["tenant_id"])
    async with session_factory() as s:
        rows = (await s.execute(select(AuditEvent).where(AuditEvent.tenant_id == tenant_id))).scalars().all()
        assert len(rows) >= 3
        assert sum(1 for r in rows if r.prev_hash == GENESIS_HASH) == 1  # exactly one genesis link
        assert len({r.entry_hash for r in rows}) == len(rows)
        # Tamper with one row's content: the chain no longer verifies from that row.
        victim = next(r for r in rows if r.action == "webhook.created")
        await s.execute(update(AuditEvent).where(AuditEvent.id == victim.id).values(summary="nothing happened"))
        await s.commit()
    verify = (await client.get(f"{API}/admin/audit/verify", headers=h)).json()
    assert verify["ok"] is False and verify["first_broken_id"] == str(victim.id)


async def test_security_event_is_audited_and_fanned_out(
    client: AsyncClient, strong_password: str, session_factory, webhook_transport: RecordingTransport
) -> None:
    h, me = await _user(client, "Sec LLP", "u@sec.co", strong_password)
    hook = await _hook(client, h, "https://siem.test/hook", ["security.lockout", "security.refresh_reuse"])
    tenant_id = uuid.UUID(me["tenant_id"])

    async with session_factory() as s:
        await emit_security_event(
            s, event_type="security.lockout", tenant_id=tenant_id, actor_id=uuid.UUID(me["id"]),
            actor_label=me["email"], summary="Account locked after 5 failed sign-ins",
            data={"attempts": 5},
        )
        await s.commit()
        assert (await verify_chain(s, tenant_id))[0]
    await dispatcher.drain()

    audit = (await client.get(f"{API}/admin/audit", headers=h, params={"action": "security.lockout"})).json()
    assert len(audit) == 1 and audit[0]["meta"] == {"attempts": 5} and audit[0]["actor_label"] == me["email"]
    deliveries = (await client.get(f"{API}/webhooks/{hook['id']}/deliveries", headers=h)).json()
    assert [d["event_type"] for d in deliveries] == ["security.lockout"]
    assert webhook_transport.calls[-1]["headers"]["X-VidhiSangh-Event"] == "security.lockout"

    # Unknown security keys are refused; tenant-less events only alert the operator.
    async with session_factory() as s:
        with pytest.raises(ValueError):
            await emit_security_event(s, event_type="matter.created", tenant_id=tenant_id, summary="x")
        await emit_security_event(s, event_type="security.refresh_reuse", tenant_id=None, summary="anon")


async def test_security_events_are_subscribable(client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "Cat LLP", "u@cat.co", strong_password)
    keys = {e["key"] for e in (await client.get(f"{API}/webhooks/events", headers=h)).json()}
    assert {"security.lockout", "security.refresh_reuse", "security.mfa_disabled", "webhook.auto_disabled"} <= keys


async def test_webhook_endpoint_breaker_columns_default(session_factory) -> None:
    async with session_factory() as s:
        cols = WebhookEndpoint.__table__.c
        assert "consecutive_failures" in cols and "auto_disabled_at" in cols
        await s.rollback()
