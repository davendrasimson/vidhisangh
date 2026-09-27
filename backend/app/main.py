"""VidhiSangh API — FastAPI application factory.

Wires configuration, structured logging, middleware (request context, security
headers, CORS, GZip), exception handlers, Prometheus metrics, health probes,
and the versioned API router. Constructed via a factory so tests can build
isolated app instances.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
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
    log.info(
        "startup",
        project=settings.PROJECT_NAME,
        version=__version__,
        environment=settings.ENVIRONMENT.value,
    )
    yield
    await close_redis()
    await dispose_engine()
    log.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{settings.PROJECT_NAME} API",
        version=__version__,
        description=(
            "Integrated legal ecosystem — networking, research, practice "
            "management, and AI productivity for legal professionals."
        ),
        docs_url=f"{settings.API_V1_PREFIX}/docs",
        redoc_url=f"{settings.API_V1_PREFIX}/redoc",
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
        lifespan=lifespan,
        swagger_ui_parameters={"persistAuthorization": True},
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

    # ── Metrics (Prometheus scrape target) ──────────────────────────
    app.mount("/metrics", make_asgi_app())

    return app


app = create_app()
