"""Liveness / readiness health probes for orchestration (K8s, load balancers),
plus an authenticated admin system-health & configuration dashboard."""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from app import __version__
from app.core.config import settings
from app.core.database import ping_database
from app.core.deps import CurrentUserDep, TenantSessionDep, require_permission
from app.core.redis import ping_redis
from app.modules.health.schemas import SystemOverview
from app.modules.health.service import SystemInfoService

router = APIRouter(tags=["Health"])
# Mounted under the versioned API prefix (unlike the root-level probes above),
# so it sits alongside the other /admin endpoints and behind authentication.
admin_router = APIRouter(tags=["Health"])


class HealthStatus(BaseModel):
    status: str
    version: str
    environment: str


class ReadinessStatus(BaseModel):
    status: str
    checks: dict[str, str]


@router.get("/health", response_model=HealthStatus, summary="Liveness probe")
async def health() -> HealthStatus:
    """Cheap liveness check — the process is up. No external dependencies."""
    return HealthStatus(
        status="ok", version=__version__, environment=settings.ENVIRONMENT.value
    )


@router.get("/ready", response_model=ReadinessStatus, summary="Readiness probe")
async def ready(response: Response) -> ReadinessStatus:
    """Readiness check — verifies critical dependencies are reachable."""
    checks: dict[str, str] = {}
    healthy = True

    try:
        await ping_database()
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {exc.__class__.__name__}"
        healthy = False

    try:
        await ping_redis()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {exc.__class__.__name__}"
        healthy = False

    response.status_code = (
        status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return ReadinessStatus(status="ok" if healthy else "degraded", checks=checks)


@admin_router.get(
    "/admin/system",
    response_model=SystemOverview,
    summary="System health & configuration (admin)",
    dependencies=[require_permission("tenant:manage")],
)
async def system_overview(
    current: CurrentUserDep, session: TenantSessionDep
) -> SystemOverview:
    """Admin diagnostics: app metadata, dependency connectivity, applied
    migration, and which optional integrations are wired (never secret values)."""
    return SystemOverview(**await SystemInfoService(session).overview())
