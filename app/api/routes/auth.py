"""Account authentication endpoints: register, login, claim-token migration,
logout, current-account info, and password change.

These routes are intentionally NOT behind ``require_token`` (except the
account-management ones that use ``require_user``) — they are the front door.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import _extract_bearer, current_user, db_session, redis_client, require_user
from app.auth import service as auth_service
from app.auth.service import AuthError
from app.core.config import settings
from app.db.models import User

logger = logging.getLogger(__name__)

router = APIRouter()


# ── schemas ───────────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str = Field(min_length=1)


class ClaimTokenRequest(BaseModel):
    email: str
    username: str
    password: str = Field(min_length=1)
    token: str
    device_name: str | None = None


class LoginRequest(BaseModel):
    identifier: str  # email or username
    password: str = Field(min_length=1)
    device_name: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=1)


class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    status: str
    is_admin: bool
    created_at: str | None = None
    approved_at: str | None = None


class SessionResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    user: UserResponse


class RegisterResponse(BaseModel):
    user: UserResponse
    # A session is only issued when the account is already approved (e.g. an
    # ADMIN_EMAILS bootstrap admin). Fresh pending signups get `token: null` and
    # must wait for admin approval before they can log in.
    token: str | None = None
    token_type: str = "bearer"
    message: str


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        email=user.email,
        username=user.username,
        status=user.status,
        is_admin=user.is_admin,
        created_at=user.created_at.isoformat() if user.created_at else None,
        approved_at=user.approved_at.isoformat() if user.approved_at else None,
    )


def _auth_http_error(exc: AuthError) -> HTTPException:
    conflict = {"email_taken", "username_taken", "token_already_claimed"}
    forbidden = {"account_pending", "account_rejected", "account_disabled", "registration_disabled"}
    if exc.code in conflict:
        code = status.HTTP_409_CONFLICT
    elif exc.code in forbidden:
        code = status.HTTP_403_FORBIDDEN
    elif exc.code == "invalid_credentials":
        code = status.HTTP_401_UNAUTHORIZED
    else:
        code = status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=code, detail={"code": exc.code, "message": exc.message})


async def _enforce_login_rate_limit(redis: Redis, identifier: str) -> None:
    """Best-effort fixed-window limiter on failed logins per identifier. Never
    blocks auth if Redis is unavailable — availability over strictness here."""
    key = f"auth:login:{identifier.strip().lower()}"
    try:
        attempts = await redis.incr(key)
        if attempts == 1:
            await redis.expire(key, settings.auth_login_rate_window_seconds)
    except Exception as exc:  # pragma: no cover - redis optional
        logger.warning("Login rate-limit check skipped (redis error): %s", exc)
        return
    if attempts > settings.auth_login_rate_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "too_many_attempts", "message": "Too many attempts. Try again later."},
        )


async def _clear_login_rate_limit(redis: Redis, identifier: str) -> None:
    try:
        await redis.delete(f"auth:login:{identifier.strip().lower()}")
    except Exception:  # pragma: no cover - redis optional
        pass


# ── routes ─────────────────────────────────────────────────────────────────────


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    session: AsyncSession = Depends(db_session),
) -> RegisterResponse:
    try:
        user = await auth_service.register_user(
            session,
            email=request.email,
            username=request.username,
            password=request.password,
        )
    except AuthError as exc:
        raise _auth_http_error(exc) from exc

    token: str | None = None
    if user.status == auth_service.STATUS_APPROVED:
        token, _ = await auth_service.create_session(session, user)
        message = "Account created."
    else:
        message = "Account created. An admin must approve it before you can log in."
    await session.commit()
    return RegisterResponse(user=_user_response(user), token=token, message=message)


@router.post("/claim-token", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def claim_token(
    request: ClaimTokenRequest,
    session: AsyncSession = Depends(db_session),
) -> SessionResponse:
    """Migrate an existing token-based user to a password account, keeping all
    their data (library, likes, plays, playlists, playback)."""
    try:
        user = await auth_service.claim_token(
            session,
            email=request.email,
            username=request.username,
            password=request.password,
            token=request.token,
        )
        token, _ = await auth_service.create_session(
            session, user, device_name=request.device_name
        )
    except AuthError as exc:
        raise _auth_http_error(exc) from exc
    await session.commit()
    return SessionResponse(token=token, user=_user_response(user))


@router.post("/login", response_model=SessionResponse)
async def login(
    request: LoginRequest,
    session: AsyncSession = Depends(db_session),
    redis: Redis = Depends(redis_client),
) -> SessionResponse:
    await _enforce_login_rate_limit(redis, request.identifier)
    try:
        user = await auth_service.authenticate(
            session, identifier=request.identifier, password=request.password
        )
    except AuthError as exc:
        raise _auth_http_error(exc) from exc
    token, _ = await auth_service.create_session(session, user, device_name=request.device_name)
    await session.commit()
    await _clear_login_rate_limit(redis, request.identifier)
    return SessionResponse(token=token, user=_user_response(user))


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(require_user)) -> UserResponse:
    return _user_response(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    _user: User = Depends(require_user),
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(db_session),
) -> None:
    token = _extract_bearer(authorization)
    if token is not None:
        await auth_service.revoke_session(session, token)
        await session.commit()


@router.post("/change-password", response_model=SessionResponse)
async def change_password(
    request: ChangePasswordRequest,
    user: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> SessionResponse:
    """Change the password, revoke all existing sessions (logs out other
    devices), and issue a fresh session for this device."""
    try:
        await auth_service.change_password(
            session,
            user,
            current_password=request.current_password,
            new_password=request.new_password,
        )
    except AuthError as exc:
        raise _auth_http_error(exc) from exc
    await auth_service.revoke_all_sessions(session, user.id)
    token, _ = await auth_service.create_session(session, user)
    await session.commit()
    return SessionResponse(token=token, user=_user_response(user))
