"""Pluggable payment gateway (Razorpay).

A provider seam so the app is gateway-agnostic and testable without live keys:

- ``mock``      — no external calls; deterministic signatures so the verify /
                  webhook flow can be tested end-to-end. Used when Razorpay keys
                  are not configured (dev / CI).
- ``razorpay``  — real Razorpay orders (via the REST API) + HMAC-SHA256 payment
                  and webhook signature verification. Activated automatically
                  when ``VS_RAZORPAY_KEY_ID`` / ``VS_RAZORPAY_KEY_SECRET`` are set.

Amounts are in the smallest currency unit (paise for INR), per Razorpay.
``get_payment_provider`` is a FastAPI dependency so it can be overridden in tests.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import uuid
from typing import Protocol, runtime_checkable

import httpx


@runtime_checkable
class PaymentProvider(Protocol):
    name: str

    @property
    def public_key(self) -> str: ...
    async def create_order(self, *, amount: int, currency: str, receipt: str) -> str: ...
    def verify_payment(self, *, order_id: str, payment_id: str, signature: str) -> bool: ...
    def verify_webhook(self, *, body: bytes, signature: str) -> bool: ...


def _hmac_sha256(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


class MockPaymentProvider:
    """Deterministic, offline provider for dev/CI (no real charges)."""

    name = "mock"
    public_key = "rzp_test_mock"
    _secret = "mock_secret"  # noqa: S105 - non-sensitive test constant

    async def create_order(self, *, amount: int, currency: str, receipt: str) -> str:
        return f"order_mock_{uuid.uuid4().hex[:14]}"

    def verify_payment(self, *, order_id: str, payment_id: str, signature: str) -> bool:
        expected = _hmac_sha256(self._secret, f"{order_id}|{payment_id}".encode())
        return hmac.compare_digest(expected, signature)

    def verify_webhook(self, *, body: bytes, signature: str) -> bool:
        return hmac.compare_digest(_hmac_sha256(self._secret, body), signature)


class RazorpayProvider:
    """Live Razorpay gateway. Order creation hits the REST API; signatures are
    verified locally with HMAC-SHA256 (Razorpay's scheme)."""

    name = "razorpay"

    def __init__(self, key_id: str, key_secret: str, webhook_secret: str) -> None:
        self._key_id = key_id
        self._key_secret = key_secret
        self._webhook_secret = webhook_secret

    @property
    def public_key(self) -> str:
        return self._key_id

    async def create_order(self, *, amount: int, currency: str, receipt: str) -> str:
        async with httpx.AsyncClient(
            base_url="https://api.razorpay.com/v1",
            auth=(self._key_id, self._key_secret),
            timeout=20,
        ) as client:
            resp = await client.post(
                "/orders",
                json={
                    "amount": amount,
                    "currency": currency,
                    "receipt": receipt,
                    "payment_capture": 1,
                },
            )
            resp.raise_for_status()
            return str(resp.json()["id"])

    def verify_payment(self, *, order_id: str, payment_id: str, signature: str) -> bool:
        # Razorpay: signature = HMAC-SHA256(order_id + "|" + payment_id, key_secret)
        expected = _hmac_sha256(self._key_secret, f"{order_id}|{payment_id}".encode())
        return hmac.compare_digest(expected, signature)

    def verify_webhook(self, *, body: bytes, signature: str) -> bool:
        # Razorpay: X-Razorpay-Signature = HMAC-SHA256(raw_body, webhook_secret)
        if not self._webhook_secret:
            return False
        return hmac.compare_digest(_hmac_sha256(self._webhook_secret, body), signature)


_provider: PaymentProvider | None = None


def get_payment_provider() -> PaymentProvider:
    """Return the configured gateway (Razorpay if keys are set, else mock)."""
    global _provider
    if _provider is None:
        key_id = os.environ.get("VS_RAZORPAY_KEY_ID")
        key_secret = os.environ.get("VS_RAZORPAY_KEY_SECRET")
        if key_id and key_secret:
            _provider = RazorpayProvider(
                key_id, key_secret, os.environ.get("VS_RAZORPAY_WEBHOOK_SECRET", "")
            )
        else:
            _provider = MockPaymentProvider()
    return _provider
