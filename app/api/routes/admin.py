"""Admin-only account approval panel.

Guarded by ``require_admin`` (an approved account with ``is_admin``). Legacy raw
API tokens have no account row and therefore cannot reach these endpoints — admin
actions require a real admin session, which keeps the approval gate from being
bypassed by a shared token.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.api.routes.auth import UserResponse, _user_response
from app.auth import service as auth_service
from app.auth.service import AuthError
from app.db.models import User

router = APIRouter(dependencies=[Depends(require_admin)])


class AdminUserListResponse(BaseModel):
    users: list[UserResponse]


def _admin_http_error(exc: AuthError) -> HTTPException:
    if exc.code == "user_not_found":
        code = status.HTTP_404_NOT_FOUND
    elif exc.code == "cannot_change_self":
        code = status.HTTP_409_CONFLICT
    else:
        code = status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=code, detail={"code": exc.code, "message": exc.message})


@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    status_filter: str | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(db_session),
) -> AdminUserListResponse:
    users = await auth_service.list_users(session, status=status_filter)
    return AdminUserListResponse(users=[_user_response(user) for user in users])


async def _set_status(
    target_user_id: UUID,
    new_status: str,
    admin: User,
    session: AsyncSession,
) -> UserResponse:
    try:
        target = await auth_service.set_user_status(
            session, target_user_id=target_user_id, status=new_status, admin=admin
        )
    except AuthError as exc:
        raise _admin_http_error(exc) from exc
    await session.commit()
    return _user_response(target)


@router.post("/users/{user_id}/approve", response_model=UserResponse)
async def approve_user(
    user_id: UUID,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
) -> UserResponse:
    return await _set_status(user_id, auth_service.STATUS_APPROVED, admin, session)


@router.post("/users/{user_id}/reject", response_model=UserResponse)
async def reject_user(
    user_id: UUID,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
) -> UserResponse:
    return await _set_status(user_id, auth_service.STATUS_REJECTED, admin, session)


@router.post("/users/{user_id}/disable", response_model=UserResponse)
async def disable_user(
    user_id: UUID,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
) -> UserResponse:
    return await _set_status(user_id, auth_service.STATUS_DISABLED, admin, session)
