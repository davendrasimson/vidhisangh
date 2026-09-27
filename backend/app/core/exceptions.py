"""Domain exception hierarchy + FastAPI exception handlers.

Domain/service code raises these framework-agnostic errors; handlers translate
them into consistent RFC-9457-style JSON problem responses. This keeps the
domain layer free of HTTP concerns (clean architecture).
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = structlog.get_logger("app.errors")


class AppError(Exception):
    """Base application error. Subclasses set ``status_code`` and ``code``."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "app_error"
    message: str = "An application error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.details = details or {}
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    message = "The requested resource was not found."


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    message = "The resource already exists or conflicts with current state."


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"
    message = "The submitted data is invalid."


class AuthenticationError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "authentication_error"
    message = "Authentication is required or has failed."


class PermissionDeniedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "permission_denied"
    message = "You do not have permission to perform this action."


class RateLimitError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"
    message = "Too many requests. Please slow down."


class TenantError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "tenant_error"
    message = "Tenant context is missing or invalid."


def _problem(
    *, status_code: int, code: str, message: str, request: Request, details: Any = None
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"https://vidhisangh.com/errors/{code}",
        "title": code,
        "status": status_code,
        "detail": message,
        "instance": str(request.url.path),
        "request_id": getattr(request.state, "request_id", None),
    }
    if details:
        body["errors"] = details
    return JSONResponse(status_code=status_code, content=body)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            log.error("app_error", code=exc.code, message=exc.message)
        return _problem(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            request=request,
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # A validator that raises ValueError leaves the exception object in
        # `ctx`, which is not JSON — strip it so the client gets a 422, not a 500.
        details = []
        for err in exc.errors():
            err = dict(err)
            ctx = err.get("ctx")
            if isinstance(ctx, dict):
                err["ctx"] = {k: (v if isinstance(v, (str, int, float, bool, type(None))) else str(v)) for k, v in ctx.items()}
            details.append(err)
        return _problem(
            status_code=422,
            code="validation_error",
            message="Request validation failed.",
            request=request,
            details=details,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _problem(
            status_code=exc.status_code,
            code="http_error",
            message=str(exc.detail),
            request=request,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_exception", error=str(exc))
        return _problem(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message="An unexpected error occurred.",
            request=request,
        )
