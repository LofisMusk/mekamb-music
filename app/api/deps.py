from collections.abc import AsyncIterator
from fastapi import Depends, Header, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import identity_for, resolve_session_token
from app.catalog.internet_archive import InternetArchiveClient
from app.catalog.lidarr_client import LidarrClient
from app.core.auth import ApiKeyIdentity, match_bearer_token
from app.core.config import settings
from app.db.models import User
from app.db.session import get_session
from app.imports.domain import ImportRepository
from app.imports.queue import RedisImportQueue
from app.imports.repository import SqlAlchemyImportRepository
from app.imports.service import ImportEventPublisher, ImportService
from app.libraries.repository import SqlAlchemyLibraryRepository
from app.libraries.service import LibraryService
from app.playlists.repository import SqlAlchemyPlaylistRepository
from app.playlists.service import PlaylistService


async def db_session() -> AsyncIterator[AsyncSession]:
    async for session in get_session():
        yield session


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


async def require_token(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(db_session),
) -> ApiKeyIdentity:
    """Resolve a request to a data-scope identity (``api_key_id``).

    Two auth schemes are accepted in parallel so existing clients keep working:
      1. Legacy raw ``API_TOKEN(S)`` bearer tokens — but only while unclaimed.
         Once a token has been migrated to an account (``/auth/claim-token``
         created a user bound to its ``api_key_id``), the raw token is dead and
         the request gets a ``token_migrated`` 401 so clients know to show the
         login screen instead of a generic auth failure.
      2. Session tokens issued by ``/auth/login`` — resolved to an *approved*
         user; pending/rejected/disabled accounts never resolve, so an
         unapproved account can never reach a protected endpoint.
    """
    api_key = match_bearer_token(settings, authorization)
    if api_key is not None:
        claimed = await session.scalar(select(User.id).where(User.api_key_id == api_key.id))
        if claimed is not None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "token_migrated",
                    "message": (
                        "This token has been migrated to an account. "
                        "Log in with your email/username and password."
                    ),
                },
            )
        return api_key

    token = _extract_bearer(authorization)
    if token is not None:
        user = await resolve_session_token(session, token)
        if user is not None:
            return identity_for(user)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid bearer token.",
    )


async def current_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(db_session),
) -> User | None:
    """The logged-in account for a session token, or ``None`` for legacy raw
    tokens (which authenticate for data access but have no account row)."""
    token = _extract_bearer(authorization)
    if token is None:
        return None
    return await resolve_session_token(session, token)


async def require_user(user: User | None = Depends(current_user)) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This endpoint requires a logged-in account.",
        )
    return user


async def require_admin(user: User = Depends(require_user)) -> User:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required.",
        )
    return user


def lidarr_client() -> LidarrClient:
    return LidarrClient.from_settings(settings)


_internet_archive_client: InternetArchiveClient | None = None


def internet_archive_client() -> InternetArchiveClient:
    global _internet_archive_client
    if _internet_archive_client is None:
        _internet_archive_client = InternetArchiveClient(redis_url=settings.redis_url)
    return _internet_archive_client


def redis_client() -> Redis:
    return RedisImportQueue.from_settings(settings).client


def import_repository(session: AsyncSession = Depends(db_session)) -> ImportRepository:
    return SqlAlchemyImportRepository(session)


async def import_event_publisher() -> AsyncIterator[ImportEventPublisher]:
    queue = RedisImportQueue.from_settings(settings)
    try:
        yield queue
    finally:
        await queue.close()


def import_service(
    repository: ImportRepository = Depends(import_repository),
    event_publisher: ImportEventPublisher = Depends(import_event_publisher),
) -> ImportService:
    return ImportService.from_settings(
        settings,
        repository=repository,
        event_publisher=event_publisher,
    )


def playlist_service(
    session: AsyncSession = Depends(db_session),
    api_key: ApiKeyIdentity = Depends(require_token),
) -> PlaylistService:
    return PlaylistService(repository=SqlAlchemyPlaylistRepository(session, api_key_id=api_key.id))


def library_service(
    session: AsyncSession = Depends(db_session),
    api_key: ApiKeyIdentity = Depends(require_token),
) -> LibraryService:
    return LibraryService(repository=SqlAlchemyLibraryRepository(session, api_key_id=api_key.id))
