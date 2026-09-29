"""Regression tests for the 2026-09 security-audit authentication findings.

A-1 lockout persists · A-2 limiter wiring · A-7 secrets / key rotation ·
A-8 mock IdP opt-in · A-9 hashed, expiring portal & KYC tokens · A-11 refresh
cookie + CSRF header · A-14 tenant-aware lookups / role check · A-18 MFA ·
A-19 API keys follow their creator · A-20 audit trail · A-21 OAuth identity ·
A-23 reuse grace bound to the user agent · A-24 reset / invite / immediate
revocation / logout · A-26 WebSocket tickets · A-27 docs & metrics · A-34
common-password deny-list.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

import pyotp
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core import crypto, oauth as oauth_seam, security
from app.core.channels import ChannelMessage, ChannelRegistry
from app.core.config import Environment, Settings, settings
from app.core.password_policy import PasswordPolicy, is_common_password
from app.core.ws_tickets import redeem_ws_ticket
from app.modules.clients.models import ClientKycRequest
from app.modules.identity.models import OAuthIdentity, User
from app.modules.identity.repository import UserRepository
from app.modules.notifications.models import NotificationChannel
from app.modules.portal.models import PortalAccess

pytestmark = pytest.mark.asyncio

API = "/api/v1"
CSRF = {"X-Requested-With": "VidhiSangh"}


# ─── helpers ────────────────────────────────────────────────────────
class RecordingEmail:
    name = "email"
    configured = True

    def __init__(self) -> None:
        self.sent: list[ChannelMessage] = []

    async def send(self, message: ChannelMessage) -> None:
        self.sent.append(message)

    def last_token(self) -> str:
        link = self.sent[-1].link or ""
        return link.rsplit("/", 1)[-1].split("?", 1)[0]


@pytest.fixture
def mailbox(monkeypatch) -> RecordingEmail:
    box = RecordingEmail()
    registry = ChannelRegistry({NotificationChannel.EMAIL: box})
    monkeypatch.setattr("app.modules.identity.service.get_channels", lambda: registry)
    return box


async def _register(client: AsyncClient, email: str, pw: str, org: str = "Hardening LLP") -> dict:
    resp = await client.post(
        f"{API}/auth/register",
        json={"organisation_name": org, "full_name": "Adv. Test", "email": email,
              "password": pw, "accept_terms": True},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _bearer(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def _login(client: AsyncClient, email: str, pw: str, **extra) -> object:
    return await client.post(f"{API}/auth/login", json={"email": email, "password": pw, **extra})


async def _audit_actions(client: AsyncClient, h: dict) -> set[str]:
    return {e["action"] for e in (await client.get(f"{API}/admin/audit", headers=h)).json()}


# ═══ A-1: the failed-login counter survives the 401 ══════════════════
async def test_lockout_engages_after_five_failures_and_blocks_the_right_password(
    client: AsyncClient, strong_password: str
) -> None:
    await _register(client, "lock@firm.co", strong_password)
    for _ in range(5):
        assert (await _login(client, "lock@firm.co", "Wrong!Pass#1")).status_code == 401
    # 6th attempt WITH the correct password: locked.
    locked = await _login(client, "lock@firm.co", strong_password)
    assert locked.status_code == 403, locked.text
    assert "locked" in locked.json()["detail"].lower()
    # The lockout and each failure are audited (committed with the counter).
    owner = await _register(client, "auditor@firm.co", strong_password, org="Other LLP")
    assert owner  # separate tenant cannot see it; check via a DB-free path below


async def test_lockout_expires_and_success_resets_the_counter(
    client: AsyncClient, strong_password: str, monkeypatch, session_factory
) -> None:
    await _register(client, "expire@firm.co", strong_password)
    for _ in range(5):
        assert (await _login(client, "expire@firm.co", "Wrong!Pass#1")).status_code == 401
    assert (await _login(client, "expire@firm.co", strong_password)).status_code == 403

    # Move the lock into the past (as time would) and sign in: works, counter reset.
    async with session_factory() as s:
        user = (await s.execute(select(User).where(User.email == "expire@firm.co"))).scalar_one()
        assert user.failed_login_count == 5 and user.locked_until is not None
        user.locked_until = datetime.now(UTC) - timedelta(seconds=1)
        await s.commit()
    ok = await _login(client, "expire@firm.co", strong_password)
    assert ok.status_code == 200, ok.text
    async with session_factory() as s:
        user = (await s.execute(select(User).where(User.email == "expire@firm.co"))).scalar_one()
        assert user.failed_login_count == 0 and user.locked_until is None
    actions = await _audit_actions(client, _bearer(ok.json()))
    assert {"auth.login_failed", "auth.lockout", "auth.login"} <= actions


async def test_bad_mfa_code_counts_towards_lockout(client: AsyncClient, strong_password: str) -> None:
    tokens = await _register(client, "mfalock@firm.co", strong_password)
    h = _bearer(tokens)
    secret = (await client.post(f"{API}/auth/mfa/enroll", headers=h)).json()["secret"]
    assert (await client.post(f"{API}/auth/mfa/enable", headers=h,
                              json={"code": pyotp.TOTP(secret).now()})).status_code == 200
    for _ in range(5):
        r = await _login(client, "mfalock@firm.co", strong_password, mfa_code="000000")
        assert r.status_code == 401
    r = await _login(client, "mfalock@firm.co", strong_password, mfa_code=pyotp.TOTP(secret).now())
    assert r.status_code == 403


# ═══ A-2: limiter wiring ═════════════════════════════════════════════
async def test_default_limiter_is_attached_to_the_api_router() -> None:
    from app.api.v1.router import api_router
    from app.core.ratelimit import default_rate_limit

    assert any(d.dependency is default_rate_limit for d in api_router.dependencies)


async def test_login_is_throttled_per_account_over_http(client: AsyncClient, strong_password: str, monkeypatch) -> None:
    from app.core import ratelimit

    await _register(client, "throttle@firm.co", strong_password)
    monkeypatch.setattr(settings, "RATE_LIMITING_ENABLED", True)
    monkeypatch.setattr(ratelimit.account_rate_limit, "times", 3)
    monkeypatch.setattr(ratelimit.auth_rate_limit, "times", 1000)
    for i in range(3):
        r = await client.post(f"{API}/auth/login", json={"email": "throttle@firm.co", "password": "Nope!1234"},
                              headers={"X-Forwarded-For": f"10.9.9.{i}"})
        assert r.status_code == 401
    r = await client.post(f"{API}/auth/login", json={"email": "THROTTLE@firm.co", "password": strong_password})
    assert r.status_code == 429, r.text
    assert r.json()["errors"]["retry_after"] >= 1


# ═══ A-7: secrets & key rotation ═════════════════════════════════════
async def test_secret_key_is_required_and_peppers_validated(monkeypatch) -> None:
    monkeypatch.delenv("VS_SECRET_KEY", raising=False)
    env = {k: v for k, v in os.environ.items() if not k.startswith("VS_")}
    with pytest.raises(Exception):
        Settings(_env_file=None, **{})  # type: ignore[call-arg]
    with pytest.raises(Exception):
        Settings(_env_file=None, SECRET_KEY="short")  # type: ignore[call-arg]
    with pytest.raises(Exception):
        Settings(_env_file=None, SECRET_KEY="x" * 40, REFRESH_TOKEN_PEPPER="tiny")  # type: ignore[call-arg]
    ok = Settings(_env_file=None, SECRET_KEY="x" * 40)  # type: ignore[call-arg]
    assert ok.refresh_token_pepper == "x" * 40  # continuity for existing hashes
    assert ok.link_token_pepper != ok.SECRET_KEY and len(ok.link_token_pepper) == 64
    assert "VS_REFRESH_TOKEN_PEPPER" in ok.derived_secrets_in_use
    assert env is not None


async def test_smtp_password_can_come_from_runtime_credential(tmp_path) -> None:
    credential = tmp_path / "smtp_password"
    credential.write_text("mail-secret\n", encoding="utf-8")
    configured = Settings(  # type: ignore[call-arg]
        _env_file=None,
        SECRET_KEY="x" * 40,
        SMTP_PASSWORD_FILE=str(credential),
    )
    assert configured.smtp_password == "mail-secret"

    explicit = Settings(  # type: ignore[call-arg]
        _env_file=None,
        SECRET_KEY="x" * 40,
        SMTP_PASSWORD="environment-secret",
        SMTP_PASSWORD_FILE=str(credential),
    )
    assert explicit.smtp_password == "environment-secret"

    missing = Settings(  # type: ignore[call-arg]
        _env_file=None,
        SECRET_KEY="x" * 40,
        SMTP_PASSWORD_FILE=str(tmp_path / "missing"),
    )
    with pytest.raises(RuntimeError, match="unavailable"):
        _ = missing.smtp_password


async def test_production_gate_rejects_hs256_and_mock_idp(monkeypatch) -> None:
    prod = Settings(  # type: ignore[call-arg]
        _env_file=None, SECRET_KEY="x" * 40, ENVIRONMENT="production", POSTGRES_PASSWORD="s3cret-pass",
        BACKEND_CORS_ORIGINS="https://vidhisangh.com", JWT_ALGORITHM="HS256", OAUTH_MOCK_ENABLED=False,
    )
    with pytest.raises(RuntimeError, match="asymmetric"):
        prod.assert_production_ready()
    mock = Settings(  # type: ignore[call-arg]
        _env_file=None, SECRET_KEY="x" * 40, ENVIRONMENT="production", OAUTH_MOCK_ENABLED=True,
    )
    with pytest.raises(RuntimeError, match="OAUTH_MOCK"):
        mock.assert_production_ready()


async def test_field_encryption_rotates_and_reads_legacy_values(monkeypatch) -> None:
    from cryptography.fernet import Fernet

    crypto.reset_keyring()
    try:
        legacy = crypto._legacy_key().encrypt(b"old secret").decode()  # no key-id prefix
        assert crypto.decrypt(legacy) == "old secret"
        assert crypto.needs_reencryption(legacy)
        # Configure two explicit keys, newest first: ids k2 (new) and k1 (old).
        k_old, k_new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
        monkeypatch.setattr(settings, "FIELD_ENCRYPTION_KEYS", f"{k_new},{k_old}")
        crypto.reset_keyring()
        assert crypto.current_key_id() == 2
        blob = crypto.encrypt("pii")
        assert blob.startswith("k2:") and crypto.decrypt(blob) == "pii"
        old_blob = "k1:" + Fernet(k_old.encode()).encrypt(b"older").decode()
        assert crypto.decrypt(old_blob) == "older" and crypto.needs_reencryption(old_blob)
        assert crypto.decrypt(legacy) == "old secret"  # SECRET_KEY-derived fallback still works
        with pytest.raises(ValueError):
            crypto.decrypt("k2:" + Fernet.generate_key().decode())
    finally:
        monkeypatch.setattr(settings, "FIELD_ENCRYPTION_KEYS", None)
        crypto.reset_keyring()


# ═══ A-8: mock IdP is opt-in ═════════════════════════════════════════
async def test_mock_provider_only_when_opted_in(client: AsyncClient, monkeypatch) -> None:
    assert "mock" in {p["name"] for p in (await client.get(f"{API}/auth/oauth/providers")).json()}
    monkeypatch.setattr(settings, "OAUTH_MOCK_ENABLED", False)
    assert "mock" not in {p["name"] for p in (await client.get(f"{API}/auth/oauth/providers")).json()}
    assert (await client.post(f"{API}/auth/oauth/mock/authorize",
                              json={"redirect_uri": "https://app.test/auth/callback"})).status_code == 404


# ═══ A-9: portal & KYC tokens ════════════════════════════════════════
async def test_portal_tokens_are_hashed_expire_and_record_use(
    client: AsyncClient, strong_password: str, session_factory
) -> None:
    h = _bearer(await _register(client, "portal@firm.co", strong_password))
    mid = (await client.post(f"{API}/matters", headers=h, json={"title": "Portal case", "client_name": "Client"})).json()["id"]
    created = await client.post(f"{API}/portal/access", headers=h,
                                json={"matter_id": mid, "client_name": "C", "client_email": "c@x.co"})
    assert created.status_code == 201, created.text
    body = created.json()
    token = body["token"]
    assert token and body["expires_at"] is not None
    # Listing never exposes the token again — only the hash is stored.
    listed = (await client.get(f"{API}/portal/access", headers=h, params={"matter_id": mid})).json()
    assert listed[0]["token"] is None
    access_id = uuid.UUID(body["id"])
    async with session_factory() as s:
        row = (await s.execute(select(PortalAccess).where(PortalAccess.id == access_id))).scalar_one()
        assert row.token is None and row.token_hash == security.hash_link_token(token)
        assert row.last_accessed_at is None
    assert (await client.get(f"{API}/portal/client/{token}")).status_code == 200
    async with session_factory() as s:
        row = (await s.execute(select(PortalAccess).where(PortalAccess.id == access_id))).scalar_one()
        assert row.last_accessed_at is not None
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await s.commit()
    expired = await client.get(f"{API}/portal/client/{token}")
    assert expired.status_code == 404 and "expired" in expired.json()["detail"].lower()


async def test_kyc_tokens_are_hashed(client: AsyncClient, strong_password: str, session_factory) -> None:
    h = _bearer(await _register(client, "kyc2@firm.co", strong_password))
    c = (await client.post(f"{API}/clients", headers=h, json={"kind": "individual", "display_name": "R"})).json()
    req = (await client.post(f"{API}/clients/{c['id']}/kyc", headers=h, json={})).json()
    token = req["url"].rsplit("/", 1)[-1]
    async with session_factory() as s:
        row = (await s.execute(select(ClientKycRequest).where(ClientKycRequest.id == uuid.UUID(req["id"])))).scalar_one()
        assert row.token is None and row.token_hash == security.hash_link_token(token)
    # Stored requests cannot rebuild the link; the raw token still opens the form.
    assert (await client.get(f"{API}/clients/{c['id']}/kyc", headers=h)).json()[0]["url"] is None
    assert (await client.get(f"{API}/kyc/{token}")).status_code == 200


# ═══ A-11: refresh cookie + CSRF header ══════════════════════════════
async def test_refresh_token_is_cookie_only_and_usable(client: AsyncClient, strong_password: str) -> None:
    resp = await client.post(f"{API}/auth/register", json={
        "organisation_name": "Cookie LLP", "full_name": "Adv. C", "email": "cookie@firm.co",
        "password": strong_password, "accept_terms": True})
    assert resp.status_code == 201
    raw_cookie = resp.headers.get("set-cookie", "")
    assert settings.REFRESH_COOKIE_NAME in raw_cookie
    assert "httponly" in raw_cookie.lower() and f"path={API}/auth" in raw_cookie.lower()
    assert "samesite=strict" in raw_cookie.lower()
    first = client.cookies.get(settings.REFRESH_COOKIE_NAME)
    assert first and resp.json()["refresh_token"] is None

    # Cookie-based refresh needs the custom header (CSRF defence)…
    assert (await client.post(f"{API}/auth/refresh", json={})).status_code == 403
    # …and works with it, rotating the cookie.
    ok = await client.post(f"{API}/auth/refresh", json={}, headers=CSRF)
    assert ok.status_code == 200, ok.text
    assert ok.json()["refresh_token"] is None
    assert client.cookies.get(settings.REFRESH_COOKIE_NAME) != first
    client.cookies.clear()
    assert (await client.post(f"{API}/auth/refresh", json={})).status_code == 401  # nothing presented


async def test_refresh_token_can_be_kept_out_of_the_body(client: AsyncClient, strong_password: str, monkeypatch) -> None:
    monkeypatch.setattr(settings, "REFRESH_TOKEN_IN_BODY", False)
    tokens = await _register(client, "nobody@firm.co", strong_password)
    assert tokens["refresh_token"] is None
    assert client.cookies.get(settings.REFRESH_COOKIE_NAME)
    refreshed = await client.post(f"{API}/auth/refresh", json={}, headers=CSRF)
    assert refreshed.status_code == 200 and refreshed.json()["refresh_token"] is None


async def test_logout_uses_cookie_or_rtid_and_reports_nothing_to_revoke(client: AsyncClient, strong_password: str) -> None:
    tokens = await _register(client, "bye@firm.co", strong_password)
    h = _bearer(tokens)
    # Cookie present (set by register) → revoked, cookie cleared.
    out = await client.post(f"{API}/auth/logout", json={}, headers={**h, **CSRF})
    assert out.status_code == 204, out.text
    assert "max-age=0" in out.headers.get("set-cookie", "").lower() or 'expires=' in out.headers.get("set-cookie", "").lower()
    # The same session again: nothing left to revoke → 400 (not a silent 204).
    client.cookies.clear()
    again = await client.post(f"{API}/auth/logout", headers=h)
    assert again.status_code == 400 and again.json()["title"] == "nothing_revoked"
    # A fresh login, then logout with no body and no cookie → revokes by the rtid claim.
    login = (await _login(client, "bye@firm.co", strong_password)).json()
    client.cookies.clear()
    assert (await client.post(f"{API}/auth/logout", headers=_bearer(login))).status_code == 204
    assert (await client.post(f"{API}/auth/refresh", json={"refresh_token": login["refresh_token"]})).status_code == 401


# ═══ A-23: grace window bound to the user agent ══════════════════════
async def test_refresh_reuse_from_another_user_agent_is_theft(
    client: AsyncClient, strong_password: str, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "REFRESH_TOKEN_IN_BODY", True)
    signup = await client.post(f"{API}/auth/register", headers={"User-Agent": "Tab/1"}, json={
        "organisation_name": "UA LLP", "full_name": "Adv. U", "email": "ua@firm.co",
        "password": strong_password, "accept_terms": True})
    assert signup.status_code == 201
    old = signup.json()["refresh_token"]
    r1 = await client.post(f"{API}/auth/refresh", json={"refresh_token": old}, headers={"User-Agent": "Tab/1"})
    assert r1.status_code == 200
    # Same token, same UA, inside the grace window: a race → fresh pair.
    r2 = await client.post(f"{API}/auth/refresh", json={"refresh_token": old}, headers={"User-Agent": "Tab/1"})
    assert r2.status_code == 200
    # A *different* UA presenting a rotated token inside the window is theft.
    r3 = await client.post(f"{API}/auth/refresh", json={"refresh_token": old}, headers={"User-Agent": "Evil/9"})
    assert r3.status_code == 401 and r3.json()["title"] == "refresh_reuse_detected"
    for t in (r1.json()["refresh_token"], r2.json()["refresh_token"]):
        assert (await client.post(f"{API}/auth/refresh", json={"refresh_token": t}, headers={"User-Agent": "Tab/1"})).status_code == 401


# ═══ A-24a: password reset ═══════════════════════════════════════════
async def test_forgot_and_reset_password(client: AsyncClient, strong_password: str, mailbox: RecordingEmail) -> None:
    tokens = await _register(client, "forgot@firm.co", strong_password)
    mailbox.sent.clear()
    # Uniform 202 for unknown and known addresses.
    assert (await client.post(f"{API}/auth/forgot-password", json={"email": "ghost@nowhere.co"})).status_code == 202
    assert mailbox.sent == []
    assert (await client.post(f"{API}/auth/forgot-password", json={"email": "Forgot@firm.co"})).status_code == 202
    assert len(mailbox.sent) == 1 and "/auth/reset/" in (mailbox.sent[0].link or "")
    token = mailbox.last_token()

    # Weak / common new passwords are refused before the token is consumed.
    assert (await client.post(f"{API}/auth/reset-password", json={"token": token, "new_password": "Password@123"})).status_code == 422
    done = await client.post(f"{API}/auth/reset-password", json={"token": token, "new_password": "Fresh!Pass#2026"})
    assert done.status_code == 204, done.text
    # Single use; old password dead; old refresh token revoked; new password works.
    assert (await client.post(f"{API}/auth/reset-password", json={"token": token, "new_password": "Another!Pass#2026"})).status_code == 404
    assert (await _login(client, "forgot@firm.co", strong_password)).status_code == 401
    assert (await client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})).status_code == 401
    ok = await _login(client, "forgot@firm.co", "Fresh!Pass#2026")
    assert ok.status_code == 200
    actions = await _audit_actions(client, _bearer(ok.json()))
    assert {"auth.password_reset_requested", "auth.password_reset"} <= actions


async def test_reset_token_expires(client: AsyncClient, strong_password: str, mailbox: RecordingEmail, session_factory) -> None:
    from app.modules.identity.models import PasswordResetToken

    await _register(client, "late@firm.co", strong_password)
    await client.post(f"{API}/auth/forgot-password", json={"email": "late@firm.co"})
    token = mailbox.last_token()
    async with session_factory() as s:
        row = (await s.execute(select(PasswordResetToken).where(
            PasswordResetToken.token_hash == security.hash_link_token(token)))).scalar_one()
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await s.commit()
    assert (await client.post(f"{API}/auth/reset-password", json={"token": token, "new_password": "Fresh!Pass#2026"})).status_code == 422


# ═══ A-24b: invitations & password_must_change ═══════════════════════
async def test_invite_returns_link_not_password_by_default(client: AsyncClient, strong_password: str, monkeypatch, mailbox) -> None:
    monkeypatch.setattr(settings, "INVITES_RETURN_TEMP_PASSWORD", False)
    h = _bearer(await _register(client, "boss@firm.co", strong_password))
    created = await client.post(f"{API}/tenants/users", headers=h,
                                json={"email": "new@firm.co", "full_name": "New Person", "role_codes": ["associate"]})
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["temporary_password"] is None
    assert body["invitation_url"] and "/auth/reset/" in body["invitation_url"]
    assert body["user"]["password_must_change"] is True
    assert "invitation_url" not in body["user"]  # never serialised on the user itself
    assert mailbox.sent and mailbox.sent[-1].link == body["invitation_url"]
    assert "user.invited" in await _audit_actions(client, h)
    token = body["invitation_url"].rsplit("/", 1)[-1].split("?", 1)[0]
    assert (await client.post(f"{API}/auth/reset-password", json={"token": token, "new_password": strong_password})).status_code == 204
    login = await _login(client, "new@firm.co", strong_password)
    assert login.status_code == 200 and login.json()["password_must_change"] is False
    me = (await client.get(f"{API}/auth/me", headers=_bearer(login.json()))).json()
    assert me["is_email_verified"] is True  # the invite reached the mailbox


async def test_temp_password_session_is_scoped_to_change_password(client: AsyncClient, strong_password: str) -> None:
    h = _bearer(await _register(client, "boss2@firm.co", strong_password))
    created = (await client.post(f"{API}/tenants/users", headers=h,
                                 json={"email": "temp@firm.co", "full_name": "Temp Person", "role_codes": ["org_admin"]})).json()
    temp = created["temporary_password"]  # INVITES_RETURN_TEMP_PASSWORD is on for the suite
    assert temp
    login = await _login(client, "temp@firm.co", temp)
    assert login.status_code == 200 and login.json()["password_must_change"] is True
    th = _bearer(login.json())
    assert (await client.get(f"{API}/matters", headers=th)).status_code == 403
    assert "change your temporary password" in (await client.get(f"{API}/matters", headers=th)).json()["detail"]
    assert (await client.get(f"{API}/auth/me", headers=th)).status_code == 200
    changed = await client.post(f"{API}/auth/change-password", headers=th,
                                json={"current_password": temp, "new_password": strong_password})
    assert changed.status_code == 204, changed.text
    login2 = await _login(client, "temp@firm.co", strong_password)
    assert login2.json()["password_must_change"] is False
    assert (await client.get(f"{API}/matters", headers=_bearer(login2.json()))).status_code == 200


# ═══ A-24c: immediate revocation via the denylist ════════════════════
async def test_role_change_and_deactivation_revoke_access_tokens_immediately(
    client: AsyncClient, strong_password: str, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "REFRESH_TOKEN_IN_BODY", True)
    owner_h = _bearer(await _register(client, "owner3@firm.co", strong_password))
    created = (await client.post(f"{API}/tenants/users", headers=owner_h,
                                 json={"email": "m3@firm.co", "full_name": "Member", "role_codes": ["org_admin"]})).json()
    token = created["invitation_url"].rsplit("/", 1)[-1].split("?", 1)[0]
    await client.post(f"{API}/auth/reset-password", json={"token": token, "new_password": strong_password})
    login = (await _login(client, "m3@firm.co", strong_password)).json()
    mh = _bearer(login)
    assert (await client.get(f"{API}/matters", headers=mh)).status_code == 200

    # Demote: the still-valid JWT is refused at once; a refresh mints a scoped-down token.
    assert (await client.put(f"{API}/tenants/users/{created['user']['id']}/roles", headers=owner_h,
                             json={"role_codes": ["student"]})).status_code == 200
    denied = await client.get(f"{API}/matters", headers=mh)
    assert denied.status_code == 401 and "revoked" in denied.json()["detail"].lower()
    fresh = await client.post(f"{API}/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert fresh.status_code == 200
    assert (await client.get(f"{API}/auth/me", headers=_bearer(fresh.json()))).status_code == 200
    assert (await client.get(f"{API}/matters", headers=_bearer(fresh.json()))).status_code == 403  # student

    # Deactivate: everything dies, including the new access token.
    assert (await client.post(f"{API}/tenants/users/{created['user']['id']}/deactivate", headers=owner_h)).status_code == 200
    assert (await client.get(f"{API}/auth/me", headers=_bearer(fresh.json()))).status_code == 401


async def test_denylist_falls_through_when_redis_is_down(client: AsyncClient, strong_password: str, monkeypatch) -> None:
    from app.core import revocation

    def boom():
        raise ConnectionError("redis down")

    tokens = await _register(client, "nored@firm.co", strong_password)
    monkeypatch.setattr(revocation, "get_redis", boom)
    assert (await client.get(f"{API}/auth/me", headers=_bearer(tokens))).status_code == 200


# ═══ A-18: MFA ═══════════════════════════════════════════════════════
async def test_mfa_disable_requires_password_and_code_and_wipes_backup_codes(client: AsyncClient, strong_password: str, session_factory) -> None:
    from app.modules.identity.models import MfaBackupCode

    tokens = await _register(client, "mfa@firm.co", strong_password)
    h = _bearer(tokens)
    secret = (await client.post(f"{API}/auth/mfa/enroll", headers=h)).json()["secret"]
    # Enrolment is pending: sign-in does not demand a code yet.
    assert (await _login(client, "mfa@firm.co", strong_password)).status_code == 200
    enabled = await client.post(f"{API}/auth/mfa/enable", headers=h, json={"code": pyotp.TOTP(secret).now()})
    assert enabled.status_code == 200, enabled.text
    codes = enabled.json()["backup_codes"]
    assert len(codes) == 10
    assert (await _login(client, "mfa@firm.co", strong_password)).status_code == 401  # mfa_required
    assert (await _login(client, "mfa@firm.co", strong_password, mfa_code=codes[0])).status_code == 200
    assert (await _login(client, "mfa@firm.co", strong_password, mfa_code=codes[0])).status_code == 401  # single use

    # Re-enrolling keeps the current authenticator working until the new one is proven.
    pending = (await client.post(f"{API}/auth/mfa/enroll", headers=h)).json()["secret"]
    assert pending != secret
    assert (await _login(client, "mfa@firm.co", strong_password, mfa_code=pyotp.TOTP(secret).now())).status_code == 200
    async with session_factory() as s:  # …but the old backup codes are gone
        assert (await s.execute(select(MfaBackupCode))).scalars().all() == []

    # Disable: password + code, both checked.
    assert (await client.post(f"{API}/auth/mfa/disable", headers=h,
                              json={"password": "Wrong!Pass#1", "code": pyotp.TOTP(secret).now()})).status_code == 401
    assert (await client.post(f"{API}/auth/mfa/disable", headers=h,
                              json={"password": strong_password, "code": "000000"})).status_code == 401
    assert (await client.post(f"{API}/auth/mfa/disable", headers=h,
                              json={"password": strong_password, "code": pyotp.TOTP(secret).now()})).status_code == 204
    me = (await client.get(f"{API}/auth/me", headers=h)).json()
    assert me["mfa_enabled"] is False
    assert (await _login(client, "mfa@firm.co", strong_password)).status_code == 200
    actions = await _audit_actions(client, h)
    assert {"auth.mfa_enrolled", "auth.mfa_enabled", "auth.mfa_disabled"} <= actions


async def test_mfa_routes_are_rate_limited_per_user(client: AsyncClient, strong_password: str, monkeypatch) -> None:
    from app.core import ratelimit

    h = _bearer(await _register(client, "mfarl@firm.co", strong_password))
    monkeypatch.setattr(settings, "RATE_LIMITING_ENABLED", True)
    monkeypatch.setattr(ratelimit.mfa_rate_limit, "times", 2)
    monkeypatch.setattr(ratelimit.default_rate_limit, "times", 1000)
    await client.post(f"{API}/auth/mfa/enroll", headers=h)
    await client.post(f"{API}/auth/mfa/enable", headers=h, json={"code": "000000"})
    assert (await client.post(f"{API}/auth/mfa/enable", headers=h, json={"code": "000000"})).status_code == 429


# ═══ A-19: API keys follow their creator ═════════════════════════════
async def test_api_key_scopes_shrink_with_creator_and_die_on_deactivation(client: AsyncClient, strong_password: str) -> None:
    owner_h = _bearer(await _register(client, "owner4@firm.co", strong_password))
    created = (await client.post(f"{API}/tenants/users", headers=owner_h,
                                 json={"email": "keyer@firm.co", "full_name": "Key Er", "role_codes": ["org_admin"]})).json()
    token = created["invitation_url"].rsplit("/", 1)[-1].split("?", 1)[0]
    await client.post(f"{API}/auth/reset-password", json={"token": token, "new_password": strong_password})
    kh = _bearer((await _login(client, "keyer@firm.co", strong_password)).json())
    expires = (datetime.now(UTC) + timedelta(days=10)).isoformat()
    raw = (await client.post(f"{API}/api-keys", headers=kh,
                             json={"name": "bot", "scopes": ["matter:read"], "expires_at": expires})).json()["key"]
    key_h = {"Authorization": f"Bearer {raw}"}
    assert (await client.get(f"{API}/matters", headers=key_h)).status_code == 200

    # Creator loses matter:read → the key's stored scope no longer applies.
    assert (await client.put(f"{API}/tenants/users/{created['user']['id']}/roles", headers=owner_h,
                             json={"role_codes": ["student"]})).status_code == 200
    assert (await client.get(f"{API}/matters", headers=key_h)).status_code == 403
    # Creator deactivated → the key is revoked outright.
    assert (await client.post(f"{API}/tenants/users/{created['user']['id']}/deactivate", headers=owner_h)).status_code == 200
    assert (await client.get(f"{API}/matters", headers=key_h)).status_code == 401
    listed = (await client.get(f"{API}/api-keys", headers=owner_h)).json()
    assert listed == [] or all(k["revoked"] for k in listed)


# ═══ A-21: OAuth identity handling ═══════════════════════════════════
async def test_oauth_rejects_foreign_redirect_and_links_identity_by_subject(client: AsyncClient, strong_password: str, session_factory) -> None:
    await _register(client, "sso2@firm.co", strong_password)
    bad = await client.post(f"{API}/auth/oauth/mock/authorize",
                            json={"redirect_uri": "https://evil.example/cb", "login_hint": "sso2@firm.co"})
    assert bad.status_code == 422
    for _ in range(2):
        state = (await client.post(f"{API}/auth/oauth/mock/authorize",
                                   json={"redirect_uri": "https://app.test/auth/callback", "login_hint": "sso2@firm.co"})).json()["state"]
        assert (await client.post(f"{API}/auth/oauth/mock/callback", json={"code": "x", "state": state})).status_code == 200
    async with session_factory() as s:
        rows = (await s.execute(select(OAuthIdentity).where(OAuthIdentity.provider == "mock"))).scalars().all()
        assert len(rows) == 1 and rows[0].subject == "mock:sso2@firm.co" and rows[0].last_used_at is not None


class _FakeIdp:
    """Stands in for a real provider: userinfo says the email is unverified, the
    id_token (already 'verified' by the fake) carries the truth."""

    def __init__(self, *, id_token: str | None, claims: dict | None = None, userinfo_verified: bool = False) -> None:
        self.id_token, self.claims, self.userinfo_verified = id_token, claims or {}, userinfo_verified
        self.nonce_seen: str | None = None

    async def exchange_code(self, cfg, *, code, code_verifier, redirect_uri):  # noqa: ANN001, ANN201
        return oauth_seam.OAuthTokens(access_token="at", id_token=self.id_token)

    async def fetch_userinfo(self, cfg, *, access_token):  # noqa: ANN001, ANN201
        return oauth_seam.OAuthUserInfo(provider=cfg.name, subject="userinfo-sub", email="sso3@firm.co",
                                        email_verified=self.userinfo_verified)

    async def verify_id_token(self, cfg, *, id_token, nonce):  # noqa: ANN001, ANN201
        self.nonce_seen = nonce
        if id_token == "bad":
            raise oauth_seam.IdTokenError("id_token rejected: signature")
        return self.claims


async def test_oauth_requires_verified_email_or_id_token(client: AsyncClient, strong_password: str, monkeypatch, session_factory) -> None:
    monkeypatch.setenv("VS_OAUTH_GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("VS_OAUTH_GOOGLE_CLIENT_SECRET", "csecret")
    await _register(client, "sso3@firm.co", strong_password)

    async def _cb() -> object:
        state = (await client.post(f"{API}/auth/oauth/google/authorize",
                                   json={"redirect_uri": "https://app.test/auth/callback"})).json()["state"]
        return await client.post(f"{API}/auth/oauth/google/callback", json={"code": "c", "state": state})

    try:
        # No id_token and userinfo does not vouch for the email → refused.
        oauth_seam.set_oauth_client(_FakeIdp(id_token=None, userinfo_verified=False))
        assert (await _cb()).status_code == 401
        # A bad id_token is refused even though userinfo would pass.
        oauth_seam.set_oauth_client(_FakeIdp(id_token="bad", userinfo_verified=True))
        assert (await _cb()).status_code == 401
        # A verified id_token links (provider, sub) and signs in; the nonce was checked.
        idp = _FakeIdp(id_token="good", claims={"sub": "google-123", "email": "sso3@firm.co", "email_verified": True})
        oauth_seam.set_oauth_client(idp)
        assert (await _cb()).status_code == 200
        assert idp.nonce_seen
        async with session_factory() as s:
            row = (await s.execute(select(OAuthIdentity).where(OAuthIdentity.provider == "google"))).scalar_one()
            assert row.subject == "google-123"
        # Subject matches even if the provider now reports a different email.
        idp2 = _FakeIdp(id_token="good", claims={"sub": "google-123", "email": "renamed@elsewhere.co", "email_verified": True})
        oauth_seam.set_oauth_client(idp2)
        assert (await _cb()).status_code == 200
    finally:
        oauth_seam.set_oauth_client(None)


async def test_userinfo_email_verified_defaults_to_false() -> None:
    assert oauth_seam._truthy(None) is False and oauth_seam._truthy("true") is True and oauth_seam._truthy(True) is True
    cfg = oauth_seam.OAuthProviderConfig(name="microsoft", display_name="MS", client_id="a", client_secret="b",
                                         authorize_url="", token_url="", userinfo_url="",
                                         issuers=("https://login.microsoftonline.com/*",))
    assert oauth_seam.issuer_allowed(cfg, "https://login.microsoftonline.com/abc/v2.0")
    assert not oauth_seam.issuer_allowed(cfg, "https://evil.example/")


# ═══ Email verification ══════════════════════════════════════════════
async def test_email_verification_link(client: AsyncClient, strong_password: str, mailbox: RecordingEmail) -> None:
    tokens = await _register(client, "verify@firm.co", strong_password)
    h = _bearer(tokens)
    assert (await client.get(f"{API}/auth/me", headers=h)).json()["is_email_verified"] is False
    assert mailbox.sent and "/auth/verify-email/" in (mailbox.sent[-1].link or "")
    token = mailbox.last_token()
    assert (await client.post(f"{API}/auth/verify-email/{token}")).status_code == 200
    assert (await client.get(f"{API}/auth/me", headers=h)).json()["is_email_verified"] is True
    assert (await client.post(f"{API}/auth/verify-email/{token}")).status_code == 404  # single use
    assert "auth.email_verified" in await _audit_actions(client, h)
    # Login was never blocked by the unverified state (product decision).


# ═══ A-14: tenant-aware lookups / role check ═════════════════════════
async def test_user_lookup_is_tenant_scoped(client: AsyncClient, strong_password: str, session_factory) -> None:
    a = await _register(client, "ta@firm.co", strong_password, org="Firm A")
    b = await _register(client, "tb@firm.co", strong_password, org="Firm B")
    a_me = (await client.get(f"{API}/auth/me", headers=_bearer(a))).json()
    b_me = (await client.get(f"{API}/auth/me", headers=_bearer(b))).json()
    async with session_factory() as s:
        repo = UserRepository(s)
        assert await repo.get_for_tenant(uuid.UUID(b_me["tenant_id"]), uuid.UUID(a_me["id"])) is None  # noqa: F811
        assert (await repo.get_for_tenant(uuid.UUID(a_me["tenant_id"]), uuid.UUID(a_me["id"]))) is not None
        assert (await repo.get_by_id_global(uuid.UUID(a_me["id"]))) is not None
    # Admin paths refuse cross-tenant ids.
    assert (await client.post(f"{API}/tenants/users/{a_me['id']}/deactivate", headers=_bearer(b))).status_code == 404


async def test_db_role_check_is_a_noop_on_sqlite(engine, monkeypatch) -> None:
    from app.core import startup_checks

    monkeypatch.setattr(startup_checks, "get_engine", lambda: engine)
    await startup_checks.assert_database_role_safe()  # SQLite → nothing to check


# ═══ A-26: WebSocket tickets ═════════════════════════════════════════
async def test_ws_ticket_is_single_use_and_checks_the_account(client: AsyncClient, strong_password: str) -> None:
    from app.modules.messaging.ws import authenticate_handshake

    tokens = await _register(client, "ws@firm.co", strong_password)
    h = _bearer(tokens)
    issued = await client.post(f"{API}/auth/ws-ticket", headers=h)
    assert issued.status_code == 200 and issued.json()["expires_in"] == settings.WS_TICKET_TTL_SECONDS
    ticket = issued.json()["ticket"]
    assert "." not in ticket  # opaque, not a JWT
    claims = await authenticate_handshake(None, ticket=ticket)
    assert claims and claims["sub"]
    assert await redeem_ws_ticket(ticket) is None  # consumed
    assert await authenticate_handshake(None, ticket="nonsense") is None
    # …but not after "sign out everywhere" (denylist) — same for a ticket minted before it.
    ticket2 = (await client.post(f"{API}/auth/ws-ticket", headers=h)).json()["ticket"]
    assert (await client.post(f"{API}/auth/logout", json={"all_devices": True}, headers=h)).status_code == 204
    assert await authenticate_handshake(None, ticket=ticket2) is None


async def test_ws_ticket_falls_back_to_signed_jwt_without_redis(client: AsyncClient, strong_password: str, monkeypatch) -> None:
    from app.core import ws_tickets

    def boom():
        raise ConnectionError("redis down")

    monkeypatch.setattr(ws_tickets, "get_redis", boom)
    h = _bearer(await _register(client, "wsjwt@firm.co", strong_password))
    ticket = (await client.post(f"{API}/auth/ws-ticket", headers=h)).json()["ticket"]
    assert ticket.count(".") == 2
    claims = await ws_tickets.redeem_ws_ticket(ticket)
    assert claims and claims["type"] == "ws"
    assert claims["exp"] - claims["iat"] <= settings.WS_TICKET_TTL_SECONDS


# ═══ A-27: docs & metrics ════════════════════════════════════════════
async def test_docs_are_off_in_production_and_metrics_need_a_token(monkeypatch) -> None:
    from app.main import create_app

    monkeypatch.setattr(settings, "ENVIRONMENT", Environment.PRODUCTION)
    monkeypatch.setattr(settings, "EXPOSE_API_DOCS", False)
    monkeypatch.setattr(settings, "METRICS_TOKEN", "metrics-secret-token")
    prod_app = create_app()
    assert prod_app.docs_url is None and prod_app.redoc_url is None and prod_app.openapi_url is None
    async with AsyncClient(transport=ASGITransport(app=prod_app), base_url="https://vidhisangh.com",
                           follow_redirects=True) as c:
        assert (await c.get("/metrics")).status_code == 401
        assert (await c.get("/metrics", headers={"Authorization": "Bearer wrong"})).status_code == 401
        ok = await c.get("/metrics", headers={"Authorization": "Bearer metrics-secret-token"})
        assert ok.status_code == 200 and b"vs_ratelimit_fallback_total" in ok.content
    monkeypatch.setattr(settings, "EXPOSE_API_DOCS", True)
    assert create_app().docs_url is not None


# ═══ A-34: common-password deny-list ═════════════════════════════════
async def test_common_passwords_are_rejected(client: AsyncClient) -> None:
    for pw in ("Password@123", "Welcome2026!", "Admin@1234", "P@ssw0rd!", "Qwerty123!"):
        assert is_common_password(pw), pw
        with pytest.raises(ValueError):
            PasswordPolicy.validate(pw)
    assert PasswordPolicy.validate("Str0ng!Pass#2026") == "Str0ng!Pass#2026"
    with pytest.raises(ValueError):
        PasswordPolicy.validate("Priya1980!Sharma", email="priya1980@firm.co")
    resp = await client.post(f"{API}/auth/register", json={
        "organisation_name": "Weak LLP", "full_name": "Weak User", "email": "weak2@firm.co",
        "password": "Password@123", "accept_terms": True})
    assert resp.status_code == 422 and "too common" in resp.text


# ═══ A-20: the security audit trail ══════════════════════════════════
async def test_credential_events_are_audited(client: AsyncClient, strong_password: str) -> None:
    tokens = await _register(client, "trail@firm.co", strong_password)
    h = _bearer(tokens)
    await _login(client, "trail@firm.co", "Wrong!Pass#1")
    login = (await _login(client, "trail@firm.co", strong_password)).json()
    sessions = (await client.get(f"{API}/auth/sessions", headers=h)).json()
    other = next(s for s in sessions if not s["is_current"])
    assert (await client.request("DELETE", f"{API}/auth/sessions/{other['id']}", headers=h)).status_code == 204
    await client.post(f"{API}/auth/passkeys/register/begin", headers=h)
    await client.post(f"{API}/auth/passkeys/register/finish", headers=h,
                      json={"name": "Key", "response": {"credential_id": "c1", "public_key": "pk"}})
    pk = (await client.get(f"{API}/auth/passkeys", headers=h)).json()[0]["id"]
    await client.request("DELETE", f"{API}/auth/passkeys/{pk}", headers=h)
    await client.post(f"{API}/auth/change-password", headers=h,
                      json={"current_password": strong_password, "new_password": "Changed!Pass#2026"})
    h2 = _bearer((await _login(client, "trail@firm.co", "Changed!Pass#2026")).json())
    actions = await _audit_actions(client, h2)
    assert {"auth.registered", "auth.login_failed", "auth.login", "auth.session_revoked",
            "auth.passkey_added", "auth.passkey_removed", "auth.password_changed"} <= actions
    assert login  # (used above)
    await asyncio.sleep(0)
