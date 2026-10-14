"""A write is only reported as saved once it is committed (FUTURE_DELIVERABLES, 11 Oct 2026).

FastAPI runs a yield-dependency's cleanup after the response by default, so a
failed commit used to reach the client as 200/201 while the change was lost.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from tests.test_research import API, _user


async def test_failed_commit_is_an_error_not_a_success(
    client: AsyncClient, strong_password: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, _ = await _user(client, "Commit LLP", "commit@firm.co", strong_password)

    async def broken_commit(self: AsyncSession) -> None:
        raise RuntimeError("database went away during commit")

    monkeypatch.setattr(AsyncSession, "commit", broken_commit)
    # Unhandled errors must come back as a 500, not be raised into the test.
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as raw:
        resp = await raw.post(f"{API}/network/posts", headers=headers, json={"content": "Will this be saved?"})
    assert resp.status_code >= 500, f"a lost write was reported as {resp.status_code}"
