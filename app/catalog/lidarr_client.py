from __future__ import annotations

import json
import logging
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger("uvicorn.error")


class LidarrError(RuntimeError):
    pass


class LidarrNotConfigured(LidarrError):
    pass


class LidarrClient:
    """Thin Lidarr API v1 client. Lidarr owns discovery, monitoring, and
    downloading; this client only performs artist/album *lookup*, *add*, and a
    reachability *status* check used by the readiness probe."""

    def __init__(
        self,
        *,
        base_url: str = "",
        api_key: str = "",
        root_folder: str = "",
        quality_profile_id: int = 1,
        metadata_profile_id: int = 1,
        timeout_seconds: int = 20,
    ) -> None:
        self.base_url = base_url.strip().rstrip("/")
        self.api_key = api_key.strip()
        self.root_folder = root_folder.strip()
        self.quality_profile_id = quality_profile_id
        self.metadata_profile_id = metadata_profile_id
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_settings(cls, settings: object) -> "LidarrClient":
        return cls(
            base_url=getattr(settings, "lidarr_url", ""),
            api_key=getattr(settings, "lidarr_api_key", ""),
            root_folder=getattr(settings, "lidarr_root_folder", ""),
            quality_profile_id=getattr(settings, "lidarr_quality_profile_id", 1),
            metadata_profile_id=getattr(settings, "lidarr_metadata_profile_id", 1),
        )

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    def _require_configured(self) -> None:
        if not self.configured:
            raise LidarrNotConfigured("Lidarr is not configured (set LIDARR_URL and LIDARR_API_KEY).")

    def _request(self, method: str, path: str, *, query: dict[str, Any] | None = None, body: Any = None) -> Any:
        self._require_configured()
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"
        data = None
        headers = {"X-Api-Key": self.api_key, "Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except HTTPError as exc:
            detail = _http_error_detail(exc)
            raise LidarrError(f"Lidarr returned HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError) as exc:
            raise LidarrError(f"Could not reach Lidarr: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise LidarrError("Lidarr returned invalid JSON.") from exc

    def system_status(self) -> Any:
        return self._request("GET", "/api/v1/system/status")

    def lookup(self, kind: str, term: str) -> list[dict[str, Any]]:
        term = term.strip()
        if not term:
            return []
        path = "/api/v1/album/lookup" if kind == "album" else "/api/v1/artist/lookup"
        payload = self._request("GET", path, query={"term": term})
        return payload if isinstance(payload, list) else []

    def add_artist(self, *, foreign_artist_id: str, artist_name: str) -> dict[str, Any]:
        body = {
            "artistName": artist_name,
            "foreignArtistId": foreign_artist_id,
            "qualityProfileId": self.quality_profile_id,
            "metadataProfileId": self.metadata_profile_id,
            "rootFolderPath": self.root_folder,
            "monitored": True,
            "addOptions": {"searchForMissingAlbums": True},
        }
        return self._request("POST", "/api/v1/artist", body=body)

    def missing_albums(self, *, page_size: int = 200) -> list[dict[str, Any]]:
        """Monitored albums Lidarr has zero track files for. Each record is an
        album resource with an embedded ``artist`` and its ``releases``."""
        payload = self._request(
            "GET",
            "/api/v1/wanted/missing",
            query={
                "pageSize": page_size,
                "sortKey": "albums.title",
                "sortDirection": "ascending",
                "monitored": "true",
                "includeArtist": "true",
            },
        )
        if isinstance(payload, dict):
            records = payload.get("records")
            return records if isinstance(records, list) else []
        return []

    def manual_import_candidates(
        self, folder: str, *, artist_id: int, album_id: int
    ) -> list[dict[str, Any]]:
        """Ask Lidarr to scan a folder *scoped to a specific album*, so its own
        matcher maps each file to the right track and reports the album release
        and parsed quality. Returns one entry per file."""
        payload = self._request(
            "GET",
            "/api/v1/manualimport",
            query={
                "folder": folder,
                "artistId": artist_id,
                "albumId": album_id,
                "filterExistingFiles": "false",
            },
        )
        return payload if isinstance(payload, list) else []

    def run_manual_import(self, files: list[dict[str, Any]], *, import_mode: str = "move") -> Any:
        return self._request(
            "POST",
            "/api/v1/command",
            body={"name": "ManualImport", "importMode": import_mode, "files": files},
        )

    def add_album(self, *, foreign_album_id: str, album_title: str, foreign_artist_id: str, artist_name: str) -> dict[str, Any]:
        body = {
            "foreignAlbumId": foreign_album_id,
            "title": album_title,
            "monitored": True,
            "addOptions": {"searchForNewAlbum": True},
            "artist": {
                "artistName": artist_name,
                "foreignArtistId": foreign_artist_id,
                "qualityProfileId": self.quality_profile_id,
                "metadataProfileId": self.metadata_profile_id,
                "rootFolderPath": self.root_folder,
                "monitored": True,
            },
        }
        return self._request("POST", "/api/v1/album", body=body)


async def check_lidarr(settings: object) -> None:
    """Readiness probe: verify Lidarr is reachable when it is enabled. A no-op
    when Lidarr is disabled so single-user/dev setups stay ready."""
    import asyncio

    if not getattr(settings, "lidarr_enabled", False):
        return
    client = LidarrClient.from_settings(settings)
    await asyncio.to_thread(client.system_status)


def _http_error_detail(exc: HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:
        return "<empty>"
    return " ".join(body.split())[:500] or "<empty>"
