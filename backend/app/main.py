"""VidhiSangh API — FastAPI application factory.

Wires configuration, structured logging, middleware (request context, security
headers, CORS, GZip), exception handlers, Prometheus metrics, health probes,
and the versioned API router. Constructed via a factory so tests can build
isolated app instances.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from prometheus_client import make_asgi_app
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import __version__
from app.core.config import settings
from app.core.database import dispose_engine
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.redis import close_redis
from app.middleware.context import RequestContextMiddleware, SecurityHeadersMiddleware
from app.modules.health.router import router as health_router

configure_logging()
log = get_logger("app.main")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings.assert_production_ready()
    from app.core.storage import assert_storage_ready

    assert_storage_ready()
    from app.core.malware import assert_malware_scanner_ready

    await assert_malware_scanner_ready()
    # Refuse to run RLS-dependent code as a SUPERUSER / BYPASSRLS role (A-14).
    from app.core.startup_checks import assert_database_role_safe

    await assert_database_role_safe()
    log.info(
        "startup",
        project=settings.PROJECT_NAME,
        version=__version__,
        environment=settings.ENVIRONMENT.value,
    )
    from app.modules.identity.registration_alerts import run_delivery_loop

    alert_task = asyncio.create_task(run_delivery_loop()) if settings.is_production else None
    try:
        yield
    finally:
        if alert_task is not None:
            alert_task.cancel()
            with suppress(asyncio.CancelledError):
                await alert_task
    from app.modules.webhooks.service import dispatcher

    await dispatcher.drain()
    await close_redis()
    await dispose_engine()
    log.info("shutdown")


def _metrics_app():
    """Prometheus scrape target. With ``VS_METRICS_TOKEN`` set, the request must
    carry ``Authorization: Bearer <token>`` (audit A-27); otherwise the edge
    proxy is the only guard (production nginx denies /metrics publicly)."""
    inner = make_asgi_app()
    token = settings.METRICS_TOKEN
    if not token:
        return inner

    import hmac

    async def guarded(scope, receive, send):
        if scope["type"] == "http":
            auth = ""
            for name, value in scope.get("headers", []):
                if name == b"authorization":
                    auth = value.decode("latin-1")
                    break
            presented = auth[7:] if auth.lower().startswith("bearer ") else ""
            if not hmac.compare_digest(presented, token):
                await send(
                    {
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [
                            (b"content-type", b"text/plain"),
                            (b"www-authenticate", b"Bearer"),
                            (b"cache-control", b"no-store"),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": b"unauthorized"})
                return
        await inner(scope, receive, send)

    return guarded


def create_app() -> FastAPI:
    # Interactive docs and the OpenAPI document are off in production unless
    # explicitly re-enabled (A-27 / I-6); never persist bearer tokens in Swagger.
    expose_docs = settings.EXPOSE_API_DOCS or not settings.is_production
    app = FastAPI(
        title=f"{settings.PROJECT_NAME} API",
        version=__version__,
        description=(
            "Integrated legal ecosystem — networking, research, practice "
            "management, and AI productivity for legal professionals."
        ),
        docs_url=f"{settings.API_V1_PREFIX}/docs" if expose_docs else None,
        redoc_url=f"{settings.API_V1_PREFIX}/redoc" if expose_docs else None,
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json" if expose_docs else None,
        lifespan=lifespan,
        swagger_ui_parameters={"persistAuthorization": False},
    )

    # ── Middleware (order matters: last added runs first) ───────────
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID"],
        )
    if settings.is_production:
        # The apex must be listed separately: Starlette matches "*.example.com"
        # with host.endswith(".example.com"), which is False for the bare
        # "example.com" — so a wildcard alone rejects our own primary domain.
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=["vidhisangh.com", "*.vidhisangh.com"],
        )
    app.add_middleware(RequestContextMiddleware)

    # ── Errors ──────────────────────────────────────────────────────
    register_exception_handlers(app)

    # ── Routes ──────────────────────────────────────────────────────
    app.include_router(health_router)
    # Imported here to avoid import cycles at module load.
    from app.api.v1.router import api_router

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    # Public HTML pages at the site root (nginx proxies /judgments/ here).
    from app.modules.research.public_pages import router as public_judgments_router

    app.include_router(public_judgments_router)
    # ... and /in/<handle>/ public profile pages (members who opted in).
    from app.modules.network.public_profiles import router as public_profiles_router

    app.include_router(public_profiles_router)
    # ... and /courts/<slug>/cause-list/ public cause-list pages (the court desk's public face).
    from app.modules.courts.public_pages import router as public_courts_router

    app.include_router(public_courts_router)

    # ── Metrics (Prometheus scrape target) ──────────────────────────
    app.mount("/metrics", _metrics_app())

    return app


app = create_app()
