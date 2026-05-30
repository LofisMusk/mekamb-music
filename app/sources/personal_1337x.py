from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Protocol


class ProviderDisabledError(RuntimeError):
    pass


class OwnershipMismatch(RuntimeError):
    pass


class MissingTorrentMetadata(RuntimeError):
    pass


class Py1337xLike(Protocol):
    base_url: str

    def search(
        self,
        query: str,
        page: int = 1,
        category: str | None = None,
        sort_by: str | None = None,
        order: str = "desc",
    ) -> Any:
        ...

    def info(self, link: str | None = None, torrent_id: str | None = None) -> Any:
        ...


@dataclass(frozen=True)
class Personal1337xSearchResult:
    name: str
    torrent_id: str
    url: str
    seeders: str
    leechers: str
    size: str
    time: str
    uploader: str
    uploader_link: str
    discovered_at: datetime

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["discovered_at"] = self.discovered_at.isoformat()
        return data


@dataclass(frozen=True)
class Personal1337xImportCandidate:
    torrent_id: str
    info_hash: str
    magnet_link: str
    uploader: str
    source_url: str
    name: str | None
    fetched_at: datetime


def _get_attr(item: object, name: str, default: str = "") -> str:
    value = getattr(item, name, default)
    if value is None:
        return default
    return str(value)


def _music_category() -> str:
    try:
        from py1337x.types import category
    except Exception:
        return "Music"
    return str(getattr(category, "MUSIC", "Music"))


def _seeders_sort() -> str:
    try:
        from py1337x.types import sort
    except Exception:
        return "seeders"
    return str(getattr(sort, "SEEDERS", "seeders"))


def _build_default_client(base_url: str) -> Py1337xLike:
    from py1337x import Py1337x

    return Py1337x(base_url=base_url)


class Personal1337xProvider:
    def __init__(
        self,
        *,
        uploader: str | None,
        base_url: str = "https://1337x.to",
        max_pages: int = 1,
        client: Py1337xLike | None = None,
        category: str | None = None,
    ) -> None:
        self.uploader = uploader.strip() if uploader else ""
        self.base_url = base_url.rstrip("/")
        self.max_pages = max(1, max_pages)
        self._client = client
        self._category = category or _music_category()

    @classmethod
    def from_settings(cls, settings: object) -> "Personal1337xProvider":
        return cls(
            uploader=getattr(settings, "personal_1337x_uploader", None),
            base_url=getattr(settings, "personal_1337x_base_url", "https://1337x.to"),
            max_pages=getattr(settings, "personal_1337x_max_pages", 1),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.uploader)

    @property
    def client(self) -> Py1337xLike:
        if self._client is None:
            self._client = _build_default_client(self.base_url)
        return self._client

    async def search(
        self,
        query: str,
        *,
        page: int = 1,
        sort_by: str | None = None,
    ) -> list[Personal1337xSearchResult]:
        self._ensure_enabled()
        if page > self.max_pages:
            return []

        selected_sort = _seeders_sort() if sort_by in (None, "seeders") else sort_by
        result = await asyncio.to_thread(
            self.client.search,
            query,
            page=page,
            category=self._category,
            sort_by=selected_sort,
            order="desc",
        )

        now = datetime.now(UTC)
        filtered: list[Personal1337xSearchResult] = []
        for item in getattr(result, "items", []):
            if not self._is_owned_by_configured_uploader(item):
                continue
            filtered.append(
                Personal1337xSearchResult(
                    name=_get_attr(item, "name"),
                    torrent_id=_get_attr(item, "torrent_id"),
                    url=_get_attr(item, "url"),
                    seeders=_get_attr(item, "seeders"),
                    leechers=_get_attr(item, "leechers"),
                    size=_get_attr(item, "size"),
                    time=_get_attr(item, "time"),
                    uploader=_get_attr(item, "uploader"),
                    uploader_link=_get_attr(item, "uploader_link"),
                    discovered_at=now,
                )
            )
        return filtered

    async def resolve_for_import(self, torrent_id: str) -> Personal1337xImportCandidate:
        self._ensure_enabled()
        torrent_id = torrent_id.strip()
        if not torrent_id:
            raise MissingTorrentMetadata("Missing torrent id.")

        info = await asyncio.to_thread(self.client.info, torrent_id=torrent_id)
        if not self._is_owned_by_configured_uploader(info):
            actual = _get_attr(info, "uploader", "<missing>")
            raise OwnershipMismatch(
                f"Torrent uploader {actual!r} does not match configured uploader {self.uploader!r}."
            )

        magnet_link = _get_attr(info, "magnet_link")
        info_hash = _get_attr(info, "info_hash")
        if not magnet_link:
            raise MissingTorrentMetadata("Torrent has no magnet link.")
        if not info_hash:
            raise MissingTorrentMetadata("Torrent has no info hash.")

        return Personal1337xImportCandidate(
            torrent_id=torrent_id,
            info_hash=info_hash,
            magnet_link=magnet_link,
            uploader=_get_attr(info, "uploader"),
            source_url=self._source_url(info, torrent_id),
            name=_get_attr(info, "name") or None,
            fetched_at=datetime.now(UTC),
        )

    def _ensure_enabled(self) -> None:
        if not self.enabled:
            raise ProviderDisabledError(
                "personal_1337x provider is disabled because PERSONAL_1337X_UPLOADER is not set."
            )

    def _is_owned_by_configured_uploader(self, item: object) -> bool:
        return _get_attr(item, "uploader") == self.uploader

    def _source_url(self, info: object, torrent_id: str) -> str:
        for attr in ("url", "link", "source_url"):
            value = _get_attr(info, attr)
            if value:
                return value
        return f"{self.base_url}/torrent/{torrent_id}/"

