"""Electronic-signature workflow tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio
API = "/api/v1"


async def _account(client: AsyncClient, password: str) -> tuple[dict[str, str], dict]:
    result = await client.post(
        f"{API}/auth/register",
        json={
            "organisation_name": "Signing Chambers",
            "full_name": "Adv. Internal Signer",
            "email": "signer@example.in",
            "password": password,
            "accept_terms": True,
        },
    )
    assert result.status_code == 201, result.text
    headers = {"Authorization": f"Bearer {result.json()['access_token']}"}
    return headers, (await client.get(f"{API}/auth/me", headers=headers)).json()


async def test_internal_signature_freezes_and_seals_document(
    client: AsyncClient, strong_password: str
) -> None:
    headers, me = await _account(client, strong_password)
    uploaded = await client.post(
        f"{API}/documents",
        headers=headers,
        files={"file": ("agreement.txt", b"Agreed final wording", "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    document = uploaded.json()
    prepared = await client.post(
        f"{API}/signing/documents/{document['id']}",
        headers=headers,
        json={
            "title": "Final agreement",
            "message": "Please sign",
            "sequential": True,
            "signers": [
                {
                    "kind": "internal",
                    "user_id": me["id"],
                    "name": me["full_name"],
                    "email": me["email"],
                }
            ],
        },
    )
    assert prepared.status_code == 201, prepared.text
    envelope = prepared.json()
    assert envelope["source_checksum"]
    assert envelope["steps"][0]["status"] == "pending"

    signed = await client.post(
        f"{API}/signing/steps/{envelope['steps'][0]['id']}/sign",
        headers=headers,
        json={
            "signed_name": me["full_name"],
            "signature_data": "data:image/png;base64," + "A" * 40,
            "consent": True,
        },
    )
    assert signed.status_code == 200, signed.text
    assert signed.json()["status"] == "completed"
    assert signed.json()["final_checksum"]
    final = await client.get(f"{API}/signing/envelopes/{envelope['id']}/download", headers=headers)
    assert final.content == b"Agreed final wording"
    certificate = await client.get(
        f"{API}/signing/envelopes/{envelope['id']}/download?certificate=true",
        headers=headers,
    )
    assert certificate.status_code == 200
    assert certificate.content.startswith(b"%PDF-1.4")


async def test_signature_requires_assigned_signer_and_consent(
    client: AsyncClient, strong_password: str
) -> None:
    headers, me = await _account(client, strong_password)
    document = (
        await client.post(
            f"{API}/documents",
            headers=headers,
            files={"file": ("order.txt", b"Order", "text/plain")},
        )
    ).json()
    envelope = (
        await client.post(
            f"{API}/signing/documents/{document['id']}",
            headers=headers,
            json={
                "title": "Order",
                "signers": [
                    {
                        "kind": "internal",
                        "user_id": me["id"],
                        "name": me["full_name"],
                        "email": me["email"],
                    }
                ],
            },
        )
    ).json()
    response = await client.post(
        f"{API}/signing/steps/{envelope['steps'][0]['id']}/sign",
        headers=headers,
        json={
            "signed_name": me["full_name"],
            "signature_data": "data:image/png;base64," + "A" * 40,
            "consent": False,
        },
    )
    assert response.status_code == 422
