"""Payments tests — order creation, signature verification, webhook reconcile.

Runs against the mock gateway (no Razorpay keys), whose signatures are
deterministic HMAC-SHA256 over the shared ``mock_secret``, so the full verify /
webhook flow is exercised without live credentials.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

API = "/api/v1"
MOCK_SECRET = "mock_secret"


def _sign(message: bytes) -> str:
    return hmac.new(MOCK_SECRET.encode(), message, hashlib.sha256).hexdigest()


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


async def _order(client: AsyncClient, h: dict, amount: int = 500000) -> dict:
    resp = await client.post(
        f"{API}/payments/orders", headers=h,
        json={"amount": amount, "description": "Retainer fee"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_order_and_signature_verification(client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "Pay LLP", "pay@firm.co", strong_password)
    order = await _order(client, h)
    assert order["provider"] == "mock"
    assert order["order_id"].startswith("order_mock_")
    assert order["key_id"] == "rzp_test_mock"
    assert order["amount"] == 500000

    payment_id = order["payment_id"]
    order_id = order["order_id"]
    rzp_payment_id = "pay_test_123"

    # A wrong signature is rejected.
    bad = await client.post(
        f"{API}/payments/{payment_id}/verify", headers=h,
        json={"razorpay_payment_id": rzp_payment_id, "razorpay_signature": "deadbeef"},
    )
    assert bad.status_code == 422

    # The correct signature marks the payment paid.
    good_sig = _sign(f"{order_id}|{rzp_payment_id}".encode())
    ok = await client.post(
        f"{API}/payments/{payment_id}/verify", headers=h,
        json={"razorpay_payment_id": rzp_payment_id, "razorpay_signature": good_sig},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "paid"
    assert ok.json()["provider_payment_id"] == rzp_payment_id
    assert ok.json()["paid_at"] is not None

    listed = await client.get(f"{API}/payments", headers=h)
    assert any(p["id"] == payment_id and p["status"] == "paid" for p in listed.json())


async def test_webhook_reconciles_payment(client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "Hook LLP", "hook@firm.co", strong_password)
    order = await _order(client, h)

    payload = {
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"id": "pay_hook_1", "order_id": order["order_id"]}}},
    }
    body = json.dumps(payload).encode()
    resp = await client.post(
        f"{API}/payments/webhook", content=body,
        headers={"X-Razorpay-Signature": _sign(body), "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # The payment is now marked paid via the webhook.
    got = await client.get(f"{API}/payments/{order['payment_id']}", headers=h)
    assert got.json()["status"] == "paid"

    # A tampered webhook body / signature is rejected.
    bad = await client.post(
        f"{API}/payments/webhook", content=body,
        headers={"X-Razorpay-Signature": "nope", "Content-Type": "application/json"},
    )
    assert bad.status_code == 403


async def test_payments_tenant_isolation(client: AsyncClient, strong_password: str) -> None:
    a_h, _ = await _user(client, "Firm A", "pa@firma.co", strong_password)
    b_h, _ = await _user(client, "Firm B", "pb@firmb.co", strong_password)
    a_order = await _order(client, a_h)

    assert (await client.get(f"{API}/payments", headers=b_h)).json() == []
    assert (await client.get(f"{API}/payments/{a_order['payment_id']}", headers=b_h)).status_code == 404
