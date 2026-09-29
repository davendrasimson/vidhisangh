"""Counsel time capture, spreadsheet validation and billing workflow."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.modules.billing.timesheets import normalise_rows

API = "/api/v1"


async def _user(client: AsyncClient, password: str) -> tuple[dict[str, str], dict]:
    response = await client.post(
        f"{API}/auth/register",
        json={
            "organisation_name": "Time Chambers",
            "full_name": "Adv. Time Keeper",
            "email": "time@chambers.test",
            "password": password,
            "accept_terms": True,
        },
    )
    assert response.status_code == 201, response.text
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    me = (await client.get(f"{API}/auth/me", headers=headers)).json()
    return headers, me


def test_csv_timesheet_rows_are_normalised() -> None:
    rows = normalise_rows(
        b"Date,Counsel Email,Matter Number,Client Name,Hours,Description,Activity Type,Billable\n"
        b"29/09/2026,lawyer@example.test,M-0042,,1.5,Drafted written submissions,Drafting,Yes\n"
        b"bad-date,lawyer@example.test,M-0042,,0,,Research,No\n",
        "time.csv",
    )
    assert rows[0].duration_minutes == 90
    assert rows[0].work_date.isoformat() == "2026-09-29"
    assert rows[0].errors == []
    assert {"Invalid date; use DD/MM/YYYY.", "Description is required."} <= set(rows[1].errors)


@pytest.mark.asyncio
async def test_time_entry_approval_and_invoice(client: AsyncClient, strong_password: str) -> None:
    headers, me = await _user(client, strong_password)
    customer = await client.post(
        f"{API}/clients",
        headers=headers,
        json={"kind": "business", "display_name": "Billing Client"},
    )
    assert customer.status_code == 201, customer.text
    matter = await client.post(
        f"{API}/matters",
        headers=headers,
        json={
            "title": "Billing Client advisory",
            "client_id": customer.json()["id"],
            "client_name": "Billing Client",
        },
    )
    assert matter.status_code == 201, matter.text
    rate = await client.post(
        f"{API}/rates",
        headers=headers,
        json={"user_id": me["id"], "basis": "hourly", "amount": 4000},
    )
    assert rate.status_code == 201, rate.text

    entry = await client.post(
        f"{API}/billing/time-entries",
        headers=headers,
        json={
            "matter_id": matter.json()["id"],
            "work_date": "2026-09-29",
            "duration_minutes": 90,
            "description": "Prepared the written opinion",
            "activity_type": "Drafting",
            "billable": True,
        },
    )
    assert entry.status_code == 201, entry.text
    assert float(entry.json()["hourly_rate"]) == 4000
    assert float(entry.json()["amount"]) == 6000

    entry_id = entry.json()["id"]
    submitted = await client.post(f"{API}/billing/time-entries/{entry_id}/submit", headers=headers)
    assert submitted.json()["status"] == "submitted"
    approved = await client.post(
        f"{API}/billing/time-entries/approve",
        headers=headers,
        json={"entry_ids": [entry_id]},
    )
    assert approved.status_code == 204, approved.text
    invoice = await client.post(
        f"{API}/billing/time-entries/invoice",
        headers=headers,
        json={"entry_ids": [entry_id], "document_type": "proforma", "tax_rate": 18},
    )
    assert invoice.status_code == 201, invoice.text
    assert float(invoice.json()["subtotal"]) == 6000
    assert invoice.json()["client_name"] == "Billing Client"

    listed = await client.get(f"{API}/billing/time-entries/all", headers=headers)
    assert listed.json()[0]["status"] == "billed"
    assert listed.json()[0]["invoice_id"] == invoice.json()["id"]

    duplicate = await client.post(
        f"{API}/billing/time-entries/invoice",
        headers=headers,
        json={"entry_ids": [entry_id], "document_type": "proforma"},
    )
    assert duplicate.status_code == 422
