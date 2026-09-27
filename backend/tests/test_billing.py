"""Billing tests — invoices, line items, GST totals, pay + reconcile."""

from __future__ import annotations

import hashlib
import hmac

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


async def test_invoice_totals_and_line_items(client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "Bill LLP", "bill@firm.co", strong_password)
    inv = await client.post(
        f"{API}/billing/invoices", headers=h,
        json={
            "client_name": "Acme Corp",
            "tax_rate": "18.00",
            "line_items": [{"description": "Legal fees", "quantity": "10", "unit_price": "2000"}],
        },
    )
    assert inv.status_code == 201, inv.text
    body = inv.json()
    assert body["invoice_number"] == "INV-0001"
    assert float(body["subtotal"]) == 20000.0
    assert float(body["tax_amount"]) == 3600.0     # 18% GST
    assert float(body["total"]) == 23600.0
    iid = body["id"]

    # Add a line item → totals recompute.
    upd = await client.post(
        f"{API}/billing/invoices/{iid}/line-items", headers=h,
        json={"description": "Filing charges", "quantity": "1", "unit_price": "1000"},
    )
    assert float(upd.json()["subtotal"]) == 21000.0
    assert float(upd.json()["total"]) == 24780.0    # 21000 + 18%

    # Remove it again.
    item_id = next(li["id"] for li in upd.json()["line_items"] if li["description"] == "Filing charges")
    back = await client.request("DELETE", f"{API}/billing/line-items/{item_id}", headers=h)
    assert float(back.json()["total"]) == 23600.0


async def test_pay_and_reconcile(client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "Collect LLP", "collect@firm.co", strong_password)
    iid = (
        await client.post(
            f"{API}/billing/invoices", headers=h,
            json={"client_name": "C", "line_items": [{"description": "Fee", "quantity": "1", "unit_price": "5000"}]},
        )
    ).json()["id"]

    # Start payment → gateway order for the invoice total (₹5000 → 500000 paise).
    order = await client.post(f"{API}/billing/invoices/{iid}/pay", headers=h)
    assert order.status_code == 200, order.text
    assert order.json()["amount"] == 500000
    payment_id, order_id = order.json()["payment_id"], order.json()["order_id"]

    # Complete the payment (mock signature) then reconcile the invoice.
    rzp_payment_id = "pay_bill_1"
    sig = _sign(f"{order_id}|{rzp_payment_id}".encode())
    verify = await client.post(
        f"{API}/payments/{payment_id}/verify", headers=h,
        json={"razorpay_payment_id": rzp_payment_id, "razorpay_signature": sig},
    )
    assert verify.json()["status"] == "paid"

    reconciled = await client.post(f"{API}/billing/invoices/{iid}/reconcile", headers=h)
    assert reconciled.status_code == 200
    assert float(reconciled.json()["amount_paid"]) == 5000.0
    assert reconciled.json()["status"] == "paid"

    # Paying a fully-paid invoice is rejected.
    assert (await client.post(f"{API}/billing/invoices/{iid}/pay", headers=h)).status_code == 422


async def test_billing_tenant_isolation(client: AsyncClient, strong_password: str) -> None:
    a_h, _ = await _user(client, "Firm A", "ba@firma.co", strong_password)
    b_h, _ = await _user(client, "Firm B", "bb@firmb.co", strong_password)
    a_inv = (await client.post(f"{API}/billing/invoices", headers=a_h, json={"client_name": "X"})).json()
    assert (await client.get(f"{API}/billing/invoices", headers=b_h)).json() == []
    assert (await client.get(f"{API}/billing/invoices/{a_inv['id']}", headers=b_h)).status_code == 404
