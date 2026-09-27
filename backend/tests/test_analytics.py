"""Analytics tests — overview aggregates across billing/matters/CRM/calendar + isolation."""

from __future__ import annotations

import hashlib
import hmac
from datetime import date, datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

API = "/api/v1"
MOCK_SECRET = "mock_secret"


def _sign(message: bytes) -> str:
    return hmac.new(MOCK_SECRET.encode(), message, hashlib.sha256).hexdigest()


async def _user(client: AsyncClient, org: str, email: str, pw: str) -> dict:
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
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _invoice(client: AsyncClient, h: dict, unit_price: str, **extra) -> dict:
    inv = await client.post(
        f"{API}/billing/invoices", headers=h,
        json={"client_name": "C", "issue_date": date.today().isoformat(),
              "line_items": [{"description": "Fee", "quantity": "1", "unit_price": unit_price}], **extra},
    )
    assert inv.status_code == 201, inv.text
    return inv.json()


async def _pay(client: AsyncClient, h: dict, invoice_id: str) -> None:
    order = (await client.post(f"{API}/billing/invoices/{invoice_id}/pay", headers=h)).json()
    rzp = "pay_analytics"
    sig = _sign(f"{order['order_id']}|{rzp}".encode())
    await client.post(f"{API}/payments/{order['payment_id']}/verify", headers=h,
                      json={"razorpay_payment_id": rzp, "razorpay_signature": sig})
    reconciled = await client.post(f"{API}/billing/invoices/{invoice_id}/reconcile", headers=h)
    assert reconciled.json()["status"] == "paid"


async def test_overview_aggregates(client: AsyncClient, strong_password: str) -> None:
    h = await _user(client, "Insight LLP", "insight@firm.co", strong_password)

    # Revenue: one fully paid (₹5000 collected), one overdue-sent (₹2000 outstanding).
    paid = await _invoice(client, h, "5000")
    await _pay(client, h, paid["id"])
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    overdue = await _invoice(client, h, "2000", due_date=yesterday)
    await client.patch(f"{API}/billing/invoices/{overdue['id']}", headers=h, json={"status": "sent"})

    # Caseload: two matters, one closed.
    m1 = (await client.post(f"{API}/matters", headers=h,
                            json={"title": "M1", "client_name": "C1", "matter_type": "litigation"})).json()
    (await client.post(f"{API}/matters", headers=h,
                       json={"title": "M2", "client_name": "C2", "matter_type": "advisory"})).json()
    await client.patch(f"{API}/matters/{m1['id']}", headers=h, json={"status": "closed"})

    # Productivity: an overdue open task + a hearing in the next 7 days.
    await client.post(f"{API}/matters/{m1['id']}/tasks", headers=h,
                      json={"title": "File reply", "due_on": yesterday})
    soon = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    await client.post(f"{API}/matters/{m1['id']}/hearings", headers=h, json={"scheduled_on": soon})

    # Pipeline: one won, one open lead with values.
    won = (await client.post(f"{API}/crm/leads", headers=h,
                             json={"name": "Won Co", "source": "referral", "estimated_value": "30000.00"})).json()
    await client.patch(f"{API}/crm/leads/{won['id']}", headers=h, json={"status": "won"})
    await client.post(f"{API}/crm/leads", headers=h,
                      json={"name": "Open Co", "source": "website", "estimated_value": "15000.00"})

    ov = await client.get(f"{API}/analytics/overview", headers=h)
    assert ov.status_code == 200, ov.text
    data = ov.json()

    rev = data["revenue"]
    assert rev["invoice_count"] == 2
    assert rev["total_invoiced"] == 7000.0
    assert rev["total_collected"] == 5000.0
    assert rev["outstanding"] == 2000.0       # the sent invoice
    assert rev["overdue_amount"] == 2000.0     # sent + due date in the past
    assert {b["key"]: b["count"] for b in rev["by_status"]} == {"paid": 1, "sent": 1}

    matters = data["matters"]
    assert matters["total"] == 2 and matters["open"] == 1
    assert {b["key"]: b["count"] for b in matters["by_status"]} == {"open": 1, "closed": 1}

    prod = data["productivity"]
    assert prod["open_tasks"] == 1 and prod["overdue_tasks"] == 1
    assert prod["hearings_next_7d"] == 1 and prod["upcoming_hearings"] == 1

    pipe = data["pipeline"]
    assert pipe["total_leads"] == 2
    assert pipe["won_count"] == 1 and pipe["won_value"] == 30000.0
    assert pipe["open_value"] == 15000.0
    assert pipe["conversion_rate"] == 1.0       # 1 won / (1 won + 0 lost)

    # This month's trend bucket carries both invoices.
    current = f"{date.today().year:04d}-{date.today().month:02d}"
    point = next(p for p in data["revenue_trend"] if p["month"] == current)
    assert point["invoiced"] == 7000.0 and point["collected"] == 5000.0
    assert len(data["revenue_trend"]) == 6


async def test_overview_tenant_isolation(client: AsyncClient, strong_password: str) -> None:
    a = await _user(client, "Firm A", "aa@firma.co", strong_password)
    b = await _user(client, "Firm B", "bb@firmb.co", strong_password)
    await _invoice(client, a, "9999")

    # Firm B sees none of Firm A's revenue.
    data = (await client.get(f"{API}/analytics/overview", headers=b)).json()
    assert data["revenue"]["invoice_count"] == 0
    assert data["revenue"]["total_invoiced"] == 0.0
