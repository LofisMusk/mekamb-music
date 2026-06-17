from collections.abc import AsyncIterator
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ApiKeyIdentity, match_bearer_token
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
from app.sources.indexers import MusicIndexerProvider
from app.sources.personal_1337x import Personal1337xProvider
from app.sources.piratebay import PirateBayProvider


async def require_token(authorization: str | None = Header(default=None)) -> ApiKeyIdentity:
    api_key = match_bearer_token(settings, authorization)
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid bearer token.",
        )
    return api_key


async def db_session() -> AsyncIterator[AsyncSession]:
    async for session in get_session():
        yield session


def personal_1337x_provider() -> Personal1337xProvider:
    return Personal1337xProvider.from_settings(settings)


def piratebay_provider() -> PirateBayProvider:
    return PirateBayProvider.from_settings(settings)


def music_indexer_provider() -> MusicIndexerProvider:
    return MusicIndexerProvider.from_settings(settings)


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


def playlist_service(
    session: AsyncSession = Depends(db_session),
    api_key: ApiKeyIdentity = Depends(require_token),
) -> PlaylistService:
    return PlaylistService(repository=SqlAlchemyPlaylistRepository(session, api_key_id=api_key.id))
