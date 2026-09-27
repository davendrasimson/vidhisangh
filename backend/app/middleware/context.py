"""Request context + security-header middleware.

``RequestContextMiddleware`` assigns each request a correlation id, binds it
(and the tenant, once authenticated) to the structlog context so every log line
is traceable, and echoes it back as ``X-Request-ID``.

``SecurityHeadersMiddleware`` applies conservative baseline security headers
(HSTS, no-sniff, frame-deny, referrer policy, a strict API CSP, and a
Permissions-Policy). Frontend HTML is served by NGINX which layers its own CSP.
"""

from __future__ import annotations

import re
from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings


# KYC and portal links carry their credential as a path segment. The path is
# bound to every log line, so the token is replaced before binding (audit
# P-12 / I-7). nginx must mask it in its own access log independently.
_TOKEN_PATH_RE = re.compile(r"/(kyc|portal/client|portal)/[^/?#]+")


def mask_token_path(path: str) -> str:
    """``/api/v1/kyc/abc123`` → ``/api/v1/kyc/<token>`` (also portal links)."""
    return _TOKEN_PATH_RE.sub(lambda m: f"/{m.group(1)}/<token>", path)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid4().hex
        request.state.request_id = request_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=mask_token_path(request.url.path),
        )
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()
        response.headers["X-Request-ID"] = request_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        # Strict CSP for API responses (JSON only — no inline execution surface).
        headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
        )
        if settings.is_production:
            headers.setdefault(
                "Strict-Transport-Security",
                "max-age=63072000; includeSubDomains; preload",
            )
        return response
