"""WebAuthn / passkey verification seam.

The cryptographic ceremony (building options, verifying attestation/assertion)
lives behind a :class:`WebAuthnVerifier` so it can be swapped for tests. The
default :class:`RealWebAuthnVerifier` lazily imports the ``webauthn`` package
(an optional dependency — install it to enable passkeys in production, and serve
over HTTPS). Tests inject a :class:`MockVerifier` via :func:`set_webauthn_verifier`,
exercising the full flow (challenge lifecycle, credential storage, token issuance)
without the library or a browser authenticator.
"""

from __future__ import annotations

import os

from app.core.config import settings
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.core.exceptions import AuthenticationError, ValidationError


@dataclass(slots=True)
class VerifiedRegistration:
    credential_id: str
    public_key: str
    sign_count: int


def rp_id() -> str:
    return settings.WEBAUTHN_RP_ID


def rp_name() -> str:
    return settings.WEBAUTHN_RP_NAME


def origin() -> str:
    return settings.WEBAUTHN_ORIGIN


@runtime_checkable
class WebAuthnVerifier(Protocol):
    def registration_options(
        self, *, challenge: str, user_id: str, user_name: str, exclude_ids: list[str]
    ) -> dict: ...

    def verify_registration(self, *, challenge: str, response: dict) -> VerifiedRegistration: ...

    def authentication_options(self, *, challenge: str, allow_ids: list[str]) -> dict: ...

    def verify_authentication(
        self, *, challenge: str, response: dict, public_key: str, sign_count: int
    ) -> int: ...


class MockVerifier:
    """Deterministic verifier for tests/dev — NEVER the production default.

    ``response`` payloads are plain dicts the client echoes back; the mock trusts
    them, so it authenticates the *flow*, not the *cryptography*."""

    def registration_options(
        self, *, challenge: str, user_id: str, user_name: str, exclude_ids: list[str]
    ) -> dict:
        return {
            "challenge": challenge,
            "rp": {"id": rp_id(), "name": rp_name()},
            "user": {"id": user_id, "name": user_name},
            "excludeCredentials": [{"id": c} for c in exclude_ids],
            "mock": True,
        }

    def verify_registration(self, *, challenge: str, response: dict) -> VerifiedRegistration:
        cred_id = response.get("credential_id")
        public_key = response.get("public_key")
        if not cred_id or not public_key:
            raise ValidationError("Malformed passkey registration response.")
        return VerifiedRegistration(cred_id, public_key, int(response.get("sign_count", 0)))

    def authentication_options(self, *, challenge: str, allow_ids: list[str]) -> dict:
        return {
            "challenge": challenge,
            "rpId": rp_id(),
            "allowCredentials": [{"id": c} for c in allow_ids],
            "mock": True,
        }

    def verify_authentication(
        self, *, challenge: str, response: dict, public_key: str, sign_count: int
    ) -> int:
        if not response.get("signature"):
            raise AuthenticationError("Malformed passkey assertion.")
        return sign_count + 1


class RealWebAuthnVerifier:
    """Production verifier backed by the ``webauthn`` package (lazy import)."""

    def _lib(self):
        try:
            import webauthn  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - depends on optional dep
            raise ValidationError(
                "Passkeys are not enabled on this server (install the 'webauthn' package)."
            ) from exc
        return webauthn

    def registration_options(
        self, *, challenge: str, user_id: str, user_name: str, exclude_ids: list[str]
    ) -> dict:  # pragma: no cover - requires the optional dependency
        webauthn = self._lib()
        import base64

        opts = webauthn.generate_registration_options(
            rp_id=rp_id(),
            rp_name=rp_name(),
            user_id=user_id.encode(),
            user_name=user_name,
            challenge=base64.urlsafe_b64decode(challenge + "==="),
        )
        return webauthn.options_to_json(opts)

    def verify_registration(self, *, challenge: str, response: dict) -> VerifiedRegistration:  # pragma: no cover
        webauthn = self._lib()
        import base64

        verification = webauthn.verify_registration_response(
            credential=response,
            expected_challenge=base64.urlsafe_b64decode(challenge + "==="),
            expected_rp_id=rp_id(),
            expected_origin=origin(),
        )
        return VerifiedRegistration(
            credential_id=base64.urlsafe_b64encode(verification.credential_id).decode().rstrip("="),
            public_key=base64.urlsafe_b64encode(verification.credential_public_key).decode().rstrip("="),
            sign_count=verification.sign_count,
        )

    def authentication_options(self, *, challenge: str, allow_ids: list[str]) -> dict:  # pragma: no cover
        webauthn = self._lib()
        import base64

        opts = webauthn.generate_authentication_options(
            rp_id=rp_id(),
            challenge=base64.urlsafe_b64decode(challenge + "==="),
        )
        return webauthn.options_to_json(opts)

    def verify_authentication(
        self, *, challenge: str, response: dict, public_key: str, sign_count: int
    ) -> int:  # pragma: no cover
        webauthn = self._lib()
        import base64

        verification = webauthn.verify_authentication_response(
            credential=response,
            expected_challenge=base64.urlsafe_b64decode(challenge + "==="),
            expected_rp_id=rp_id(),
            expected_origin=origin(),
            credential_public_key=base64.urlsafe_b64decode(public_key + "==="),
            credential_current_sign_count=sign_count,
        )
        return verification.new_sign_count


_verifier: WebAuthnVerifier | None = None


def get_webauthn_verifier() -> WebAuthnVerifier:
    global _verifier
    if _verifier is None:
        _verifier = RealWebAuthnVerifier()
    return _verifier


def set_webauthn_verifier(verifier: WebAuthnVerifier | None) -> None:
    global _verifier
    _verifier = verifier
