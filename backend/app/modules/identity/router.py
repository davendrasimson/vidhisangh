"""Identity & authentication HTTP endpoints.

Refresh-token custody (audit A-11): every response that issues a token pair
also sets the refresh token as an ``HttpOnly`` cookie scoped to the auth path
(``<API_V1_PREFIX>/auth``), ``SameSite=Strict`` and ``Secure`` outside local
dev. ``/auth/refresh`` and ``/auth/logout`` read it from the cookie when the
body carries none; cookie-based calls must also send
``X-Requested-With: VidhiSangh`` (a custom header a cross-site form cannot
set — the CSRF defence). The body token keeps working for clients that still
store it themselves.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.config import settings
from app.core.deps import (
    AuthSessionDep,
    CurrentUserDep,
    TenantSessionDep,
    client_ip,
)
from app.core.exceptions import AppError, AuthenticationError, PermissionDeniedError
from app.core.ratelimit import (
    account_rate_limit,
    auth_rate_limit,
    mfa_rate_limit,
    refresh_rate_limit,
    register_rate_limit,
)
from app.core.ws_tickets import issue_ws_ticket
from app.modules.identity.models import User
from app.modules.identity.oauth_service import OAuthService
from app.modules.identity.passkey_service import PasskeyService
from app.modules.identity.repository import UserRepository
from app.modules.identity.schemas import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    MfaDisableRequest,
    MfaEnableResponse,
    MfaEnrollResponse,
    MfaVerifyRequest,
    OAuthAuthorizeRequest,
    OAuthAuthorizeResponse,
    OAuthCallbackRequest,
    OAuthProviderRead,
    PasskeyAuthBegin,
    PasskeyAuthFinish,
    PasskeyRead,
    PasskeyRegisterFinish,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SessionRead,
    TermsAcceptanceRequest,
    TokenPair,
    UserRead,
    WsTicketResponse,
)
from app.modules.identity.service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])

CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "VidhiSangh"


class NothingToRevokeError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "nothing_revoked"
    message = "No active session matched the request; nothing was signed out."


def _ua(request: Request) -> str | None:
    return request.headers.get("user-agent")


# ─── Refresh-token cookie helpers ───────────────────────────────────
def _cookie_path() -> str:
    return f"{settings.API_V1_PREFIX}/auth"


def set_refresh_cookie(response: Response, raw_refresh: str) -> None:
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=raw_refresh,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path=_cookie_path(),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        path=_cookie_path(),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


def deliver_tokens(pair: TokenPair, response: Response) -> TokenPair:
    """Move the refresh token into the cookie (and out of the body when configured)."""
    if pair.refresh_token:
        set_refresh_cookie(response, pair.refresh_token)
        if not settings.REFRESH_TOKEN_IN_BODY:
            pair.refresh_token = None
    return pair


def _require_csrf_header(request: Request) -> None:
    if request.headers.get(CSRF_HEADER, "").strip().lower() != CSRF_VALUE.lower():
        raise PermissionDeniedError(
            f"Cookie-based auth calls must send the '{CSRF_HEADER}: {CSRF_VALUE}' header."
        )


def _refresh_from_request(request: Request, body_token: str | None) -> str | None:
    """Body token first (legacy clients); else the cookie, which needs the CSRF header."""
    if body_token:
        return body_token
    cookie = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if cookie:
        _require_csrf_header(request)
    return cookie or None


async def _current_user_row(current: CurrentUserDep, session: TenantSessionDep) -> User:
    user = await UserRepository(session).get_for_tenant(current.tenant_id, current.id)
    if user is None:
        raise AuthenticationError("Account is no longer active.")
    return user


# ─── Registration / login / refresh ─────────────────────────────────
@router.post(
    "/register",
    response_model=TokenPair,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new organisation and its owner account",
    dependencies=[Depends(register_rate_limit), Depends(auth_rate_limit)],
)
async def register(
    data: RegisterRequest, request: Request, response: Response, session: AuthSessionDep
) -> TokenPair:
    _user, pair = await AuthService(session).register(
        data, ip=client_ip(request), user_agent=_ua(request)
    )
    return deliver_tokens(pair, response)


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Authenticate with email + password (and MFA if enabled)",
    dependencies=[Depends(auth_rate_limit), Depends(account_rate_limit)],
    responses={401: {"description": "Invalid credentials or MFA required."}},
)
async def login(
    data: LoginRequest, request: Request, response: Response, session: AuthSessionDep
) -> TokenPair:
    pair = await AuthService(session).login(data, ip=client_ip(request), user_agent=_ua(request))
    return deliver_tokens(pair, response)


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Exchange a refresh token (cookie or body) for a new token pair (rotating)",
    dependencies=[Depends(refresh_rate_limit)],
)
async def refresh(
    request: Request,
    response: Response,
    session: AuthSessionDep,
    data: RefreshRequest | None = None,
) -> TokenPair:
    raw = _refresh_from_request(request, data.refresh_token if data else None)
    if not raw:
        raise AuthenticationError("No refresh token was presented.")
    pair = await AuthService(session).refresh(raw, ip=client_ip(request), user_agent=_ua(request))
    return deliver_tokens(pair, response)


# ─── Password reset / email verification ────────────────────────────
@router.post(
    "/forgot-password",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Email a single-use password-reset link (uniform response)",
    dependencies=[Depends(auth_rate_limit), Depends(account_rate_limit)],
)
async def forgot_password(
    data: ForgotPasswordRequest, request: Request, session: AuthSessionDep
) -> dict[str, str]:
    await AuthService(session).request_password_reset(str(data.email), ip=client_ip(request))
    return {
        "detail": (
            "If an account exists for that address, a reset link has been sent. "
            f"It expires in {settings.PASSWORD_RESET_EXPIRE_MINUTES} minutes."
        )
    }


@router.post(
    "/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Set a new password with a reset/invitation token (signs out every session)",
    dependencies=[Depends(auth_rate_limit)],
)
async def reset_password(
    data: ResetPasswordRequest, request: Request, session: AuthSessionDep
) -> Response:
    await AuthService(session).reset_password(data.token, data.new_password, ip=client_ip(request))
    resp = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_refresh_cookie(resp)
    return resp


@router.post(
    "/verify-email/{token}",
    summary="Confirm an email address from the emailed link",
    dependencies=[Depends(auth_rate_limit)],
)
async def verify_email(token: str, session: AuthSessionDep) -> dict[str, bool]:
    await AuthService(session).verify_email(token)
    return {"verified": True}


@router.post(
    "/resend-verification",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Send a fresh email-verification link to the signed-in user",
    dependencies=[Depends(mfa_rate_limit)],
)
async def resend_verification(current: CurrentUserDep, session: TenantSessionDep) -> dict[str, str]:
    user = await _current_user_row(current, session)
    if user.is_email_verified:
        return {"detail": "This email address is already verified."}
    await AuthService(session).send_email_verification(user)
    return {"detail": "Verification email sent."}


# ─── SSO ────────────────────────────────────────────────────────────
@router.get(
    "/oauth/providers",
    response_model=list[OAuthProviderRead],
    summary="Configured SSO providers",
)
async def oauth_providers(session: AuthSessionDep) -> list[OAuthProviderRead]:
    return [OAuthProviderRead(**p) for p in OAuthService(session).list_providers()]


@router.post(
    "/oauth/{provider}/authorize",
    response_model=OAuthAuthorizeResponse,
    summary="Begin SSO — get the provider authorization URL",
    dependencies=[Depends(auth_rate_limit)],
)
async def oauth_authorize(
    provider: str, data: OAuthAuthorizeRequest, session: AuthSessionDep
) -> OAuthAuthorizeResponse:
    result = await OAuthService(session).authorize(
        provider, data.redirect_uri, data.login_hint
    )
    return OAuthAuthorizeResponse(**result)


@router.post(
    "/oauth/{provider}/callback",
    response_model=TokenPair,
    summary="Complete SSO — exchange the code for a token pair",
    dependencies=[Depends(auth_rate_limit)],
    responses={401: {"description": "Invalid state/code."}, 403: {"description": "No linked account."}},
)
async def oauth_callback(
    provider: str,
    data: OAuthCallbackRequest,
    request: Request,
    response: Response,
    session: AuthSessionDep,
) -> TokenPair:
    pair = await OAuthService(session).callback(
        provider, data.code, data.state, ip=client_ip(request), user_agent=_ua(request)
    )
    return deliver_tokens(pair, response)


# ─── Passkeys ───────────────────────────────────────────────────────
@router.post("/passkeys/register/begin", summary="Begin registering a passkey")
async def passkey_register_begin(
    current: CurrentUserDep, session: TenantSessionDep
) -> dict:
    return await PasskeyService(session).register_begin(current)


@router.post(
    "/passkeys/register/finish",
    response_model=PasskeyRead,
    status_code=status.HTTP_201_CREATED,
    summary="Finish registering a passkey",
)
async def passkey_register_finish(
    data: PasskeyRegisterFinish, current: CurrentUserDep, session: TenantSessionDep
) -> PasskeyRead:
    credential = await PasskeyService(session).register_finish(current, data.name, data.response)
    return PasskeyRead.model_validate(credential)


@router.get("/passkeys", response_model=list[PasskeyRead], summary="My registered passkeys")
async def passkey_list(current: CurrentUserDep, session: TenantSessionDep) -> list[PasskeyRead]:
    return [PasskeyRead.model_validate(c) for c in await PasskeyService(session).list(current)]


@router.delete(
    "/passkeys/{credential_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a passkey",
)
async def passkey_delete(
    credential_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await PasskeyService(session).delete(current, credential_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/passkeys/authenticate/begin",
    summary="Begin passkey sign-in",
    dependencies=[Depends(auth_rate_limit), Depends(account_rate_limit)],
)
async def passkey_auth_begin(data: PasskeyAuthBegin, session: AuthSessionDep) -> dict:
    return await PasskeyService(session).authenticate_begin(data.email)


@router.post(
    "/passkeys/authenticate/finish",
    response_model=TokenPair,
    summary="Finish passkey sign-in",
    dependencies=[Depends(auth_rate_limit)],
)
async def passkey_auth_finish(
    data: PasskeyAuthFinish, request: Request, response: Response, session: AuthSessionDep
) -> TokenPair:
    pair = await PasskeyService(session).authenticate_finish(
        data.response, ip=client_ip(request), user_agent=_ua(request)
    )
    return deliver_tokens(pair, response)


# ─── Sessions ───────────────────────────────────────────────────────
@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the current (or all) sessions",
    responses={400: {"description": "Nothing matched — no session was revoked."}},
)
async def logout(
    request: Request,
    current: CurrentUserDep,
    session: AuthSessionDep,
    data: LogoutRequest | None = None,
) -> Response:
    body = data or LogoutRequest()
    # "Everywhere" needs no token at all; otherwise body token, else the cookie
    # (which requires the CSRF header), else the session named by the JWT.
    raw = None if body.all_devices else _refresh_from_request(request, body.refresh_token)
    revoked = await AuthService(session).logout(
        current.id,
        raw_refresh=raw,
        all_devices=body.all_devices,
        session_id=current.session_id,
    )
    if revoked == 0:
        raise NothingToRevokeError()
    resp = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_refresh_cookie(resp)
    return resp


@router.post(
    "/ws-ticket",
    response_model=WsTicketResponse,
    summary="Short-lived single-use ticket for the WebSocket handshake",
)
async def ws_ticket(current: CurrentUserDep) -> WsTicketResponse:
    ticket, ttl = await issue_ws_ticket(current)
    return WsTicketResponse(ticket=ticket, expires_in=ttl)


@router.get(
    "/sessions",
    response_model=list[SessionRead],
    summary="My active sessions / signed-in devices",
)
async def list_sessions(current: CurrentUserDep, session: TenantSessionDep) -> list[SessionRead]:
    tokens = await AuthService(session).list_sessions(current.id)
    out: list[SessionRead] = []
    for t in tokens:
        s = SessionRead.model_validate(t)
        s.is_current = current.session_id is not None and t.id == current.session_id
        out.append(s)
    return out


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a session (sign out that device)",
)
async def revoke_session(
    session_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await AuthService(session).revoke_session(current.id, session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/sessions/revoke-others",
    summary="Sign out of all other devices (keeps this session)",
)
async def revoke_other_sessions(
    current: CurrentUserDep, session: TenantSessionDep
) -> dict[str, int]:
    revoked = await AuthService(session).revoke_other_sessions(current.id, current.session_id)
    return {"revoked": revoked}


@router.get("/me", response_model=UserRead, summary="Current authenticated user")
async def me(current: CurrentUserDep, session: TenantSessionDep) -> UserRead:
    return UserRead.model_validate(await _current_user_row(current, session))


@router.post(
    "/me/accept-terms",
    response_model=UserRead,
    summary="Accept the current Terms and Privacy Notice",
)
async def accept_terms(
    data: TermsAcceptanceRequest,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> UserRead:
    user = await _current_user_row(current, session)
    user = await AuthService(session).accept_current_terms(user)
    return UserRead.model_validate(user)


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change password (revokes all sessions)",
)
async def change_password(
    data: ChangePasswordRequest, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    user = await _current_user_row(current, session)
    await AuthService(session).change_password(user, data)
    resp = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_refresh_cookie(resp)
    return resp


# ─── MFA ────────────────────────────────────────────────────────────
@router.post(
    "/mfa/enroll",
    response_model=MfaEnrollResponse,
    summary="Begin TOTP enrolment",
    dependencies=[Depends(mfa_rate_limit)],
)
async def mfa_enroll(current: CurrentUserDep, session: TenantSessionDep) -> MfaEnrollResponse:
    user = await _current_user_row(current, session)
    return await AuthService(session).mfa_enroll(user)


@router.post(
    "/mfa/enable",
    response_model=MfaEnableResponse,
    summary="Confirm & enable MFA",
    dependencies=[Depends(mfa_rate_limit)],
)
async def mfa_enable(
    data: MfaVerifyRequest, current: CurrentUserDep, session: TenantSessionDep
) -> MfaEnableResponse:
    user = await _current_user_row(current, session)
    return await AuthService(session).mfa_enable(user, data.code)


@router.post(
    "/mfa/disable",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Disable MFA (requires the current password and a valid code)",
    dependencies=[Depends(mfa_rate_limit)],
)
async def mfa_disable(
    data: MfaDisableRequest, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    user = await _current_user_row(current, session)
    await AuthService(session).mfa_disable(user, password=data.password, code=data.code)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
