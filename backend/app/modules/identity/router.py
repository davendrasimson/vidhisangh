"""Identity & authentication HTTP endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.deps import (
    AuthSessionDep,
    CurrentUserDep,
    TenantSessionDep,
    client_ip,
)
from app.core.ratelimit import auth_rate_limit, refresh_rate_limit
from app.modules.identity.repository import UserRepository
import uuid

from app.modules.identity.oauth_service import OAuthService
from app.modules.identity.passkey_service import PasskeyService
from app.modules.identity.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    LogoutRequest,
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
    SessionRead,
    TokenPair,
    UserRead,
)
from app.modules.identity.service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _ua(request: Request) -> str | None:
    return request.headers.get("user-agent")


@router.post(
    "/register",
    response_model=TokenPair,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new organisation and its owner account",
    dependencies=[Depends(auth_rate_limit)],
)
async def register(
    data: RegisterRequest, request: Request, session: AuthSessionDep
) -> TokenPair:
    _user, pair = await AuthService(session).register(
        data, ip=client_ip(request), user_agent=_ua(request)
    )
    return pair


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Authenticate with email + password (and MFA if enabled)",
    dependencies=[Depends(auth_rate_limit)],
    responses={401: {"description": "Invalid credentials or MFA required."}},
)
async def login(
    data: LoginRequest, request: Request, session: AuthSessionDep
) -> TokenPair:
    return await AuthService(session).login(
        data, ip=client_ip(request), user_agent=_ua(request)
    )


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Exchange a refresh token for a new token pair (rotating)",
    dependencies=[Depends(refresh_rate_limit)],
)
async def refresh(
    data: RefreshRequest, request: Request, session: AuthSessionDep
) -> TokenPair:
    return await AuthService(session).refresh(
        data.refresh_token, ip=client_ip(request), user_agent=_ua(request)
    )


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
    provider: str, data: OAuthCallbackRequest, request: Request, session: AuthSessionDep
) -> TokenPair:
    return await OAuthService(session).callback(
        provider, data.code, data.state, ip=client_ip(request), user_agent=_ua(request)
    )


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
    dependencies=[Depends(auth_rate_limit)],
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
    data: PasskeyAuthFinish, request: Request, session: AuthSessionDep
) -> TokenPair:
    return await PasskeyService(session).authenticate_finish(
        data.response, ip=client_ip(request), user_agent=_ua(request)
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the current (or all) refresh tokens",
)
async def logout(
    data: LogoutRequest, current: CurrentUserDep, session: AuthSessionDep
) -> Response:
    await AuthService(session).logout(
        current.id, raw_refresh=data.refresh_token, all_devices=data.all_devices
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    user = await UserRepository(session).get_by_id(current.id)
    if user is None:
        from app.core.exceptions import AuthenticationError

        raise AuthenticationError("Account is no longer active.")
    return UserRead.model_validate(user)


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change password (revokes all sessions)",
)
async def change_password(
    data: ChangePasswordRequest, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    user = await UserRepository(session).get_by_id(current.id)
    if user is None:
        from app.core.exceptions import AuthenticationError

        raise AuthenticationError("Account is no longer active.")
    await AuthService(session).change_password(user, data)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── MFA ────────────────────────────────────────────────────────────
@router.post("/mfa/enroll", response_model=MfaEnrollResponse, summary="Begin TOTP enrolment")
async def mfa_enroll(current: CurrentUserDep, session: TenantSessionDep) -> MfaEnrollResponse:
    user = await UserRepository(session).get_by_id(current.id)
    if user is None:
        from app.core.exceptions import AuthenticationError

        raise AuthenticationError("Account is no longer active.")
    return await AuthService(session).mfa_enroll(user)


@router.post("/mfa/enable", response_model=MfaEnableResponse, summary="Confirm & enable MFA")
async def mfa_enable(
    data: MfaVerifyRequest, current: CurrentUserDep, session: TenantSessionDep
) -> MfaEnableResponse:
    user = await UserRepository(session).get_by_id(current.id)
    if user is None:
        from app.core.exceptions import AuthenticationError

        raise AuthenticationError("Account is no longer active.")
    return await AuthService(session).mfa_enable(user, data.code)


@router.post(
    "/mfa/disable",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Disable MFA for the current user",
)
async def mfa_disable(current: CurrentUserDep, session: TenantSessionDep) -> Response:
    user = await UserRepository(session).get_by_id(current.id)
    if user is None:
        from app.core.exceptions import AuthenticationError

        raise AuthenticationError("Account is no longer active.")
    await AuthService(session).mfa_disable(user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
