from collections.abc import AsyncIterator
from secrets import compare_digest

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.downloads.qbittorrent import QBittorrentDownloader
from app.downloads.service import DownloadService
from app.imports.domain import ImportRepository
from app.imports.queue import RedisImportQueue
from app.imports.repository import SqlAlchemyImportRepository
from app.imports.service import ImportEventPublisher, ImportService
from app.playlists.repository import SqlAlchemyPlaylistRepository
from app.playlists.service import PlaylistService
from app.sources.personal_1337x import Personal1337xProvider


async def require_token(authorization: str | None = Header(default=None)) -> None:
    expected = f"Bearer {settings.api_token}"
    if not settings.api_token or not authorization or not compare_digest(authorization, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid bearer token.",
        )


async def db_session() -> AsyncIterator[AsyncSession]:
    async for session in get_session():
        yield session


def personal_1337x_provider() -> Personal1337xProvider:
    return Personal1337xProvider.from_settings(settings)


def torrent_downloader() -> QBittorrentDownloader:
    return QBittorrentDownloader.from_settings(settings)


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
    downloader: QBittorrentDownloader = Depends(torrent_downloader),
    event_publisher: ImportEventPublisher = Depends(import_event_publisher),
) -> ImportService:
    return ImportService.from_settings(
        settings,
        repository=repository,
        downloader=downloader,
        event_publisher=event_publisher,
    )


def download_service(
    repository: ImportRepository = Depends(import_repository),
    downloader: QBittorrentDownloader = Depends(torrent_downloader),
) -> DownloadService:
    return DownloadService(repository=repository, torrent_client=downloader)


def playlist_service(session: AsyncSession = Depends(db_session)) -> PlaylistService:
    return PlaylistService(repository=SqlAlchemyPlaylistRepository(session))
