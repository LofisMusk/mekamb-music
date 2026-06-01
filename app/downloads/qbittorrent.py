from pathlib import Path
import json

import httpx

from app.downloads.domain import TorrentRuntimeStatus


class QBittorrentError(RuntimeError):
    pass


class QBittorrentAuthError(QBittorrentError):
    pass


class QBittorrentDownloader:
    def __init__(
        self,
        *,
        rpc_url: str,
        username: str,
        password: str,
        listen_port: int = 6881,
        timeout_seconds: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.rpc_url = rpc_url.rstrip("/")
        self.username = username
        self.password = password
        self.listen_port = listen_port
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    @classmethod
    def from_settings(cls, settings: object) -> "QBittorrentDownloader":
        return cls(
            rpc_url=getattr(settings, "torrent_rpc_url"),
            username=getattr(settings, "torrent_rpc_username"),
            password=getattr(settings, "torrent_rpc_password"),
            listen_port=getattr(settings, "torrent_listen_port", 6881),
        )

    async def enqueue(self, *, magnet_link: str, download_path: Path, label: str) -> None:
        async with self._client() as client:
            await self._login(client)
            await self._configure_preferences(client)
            response = await client.post(
                f"{self.rpc_url}/api/v2/torrents/add",
                data={
                    "urls": magnet_link,
                    "savepath": str(download_path),
                    "category": "mekamb-music",
                    "tags": label,
                    "paused": "false",
                    "ratioLimit": "0",
                    "seedingTimeLimit": "0",
                },
            )
            response.raise_for_status()

    async def status_by_label(self, label: str) -> TorrentRuntimeStatus | None:
        async with self._client() as client:
            await self._login(client)
            await self._configure_preferences(client)
            response = await client.get(
                f"{self.rpc_url}/api/v2/torrents/info",
                params={"tag": label},
            )
            response.raise_for_status()

        payload = response.json()
        if not isinstance(payload, list):
            raise QBittorrentError("qBittorrent returned an unexpected torrent info response.")
        if not payload:
            return None
        if not isinstance(payload[0], dict):
            raise QBittorrentError("qBittorrent torrent info item has an unexpected shape.")
        return TorrentRuntimeStatus.from_qbittorrent(payload[0])

    async def delete_by_label(self, label: str, *, delete_files: bool) -> bool:
        async with self._client() as client:
            await self._login(client)
            response = await client.get(
                f"{self.rpc_url}/api/v2/torrents/info",
                params={"tag": label},
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                raise QBittorrentError("qBittorrent returned an unexpected torrent info response.")
            hashes = [
                str(item.get("hash"))
                for item in payload
                if isinstance(item, dict) and item.get("hash")
            ]
            if not hashes:
                return False

            delete_response = await client.post(
                f"{self.rpc_url}/api/v2/torrents/delete",
                data={
                    "hashes": "|".join(hashes),
                    "deleteFiles": "true" if delete_files else "false",
                },
            )
            delete_response.raise_for_status()
            return True

    async def check(self) -> None:
        async with self._client() as client:
            await self._login(client)
            await self._configure_preferences(client)
            response = await client.get(f"{self.rpc_url}/api/v2/app/version")
            response.raise_for_status()
            if not response.text.strip():
                raise QBittorrentError("qBittorrent returned an empty version response.")

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout_seconds, transport=self.transport)

    async def _login(self, client: httpx.AsyncClient) -> None:
        login = await client.post(
            f"{self.rpc_url}/api/v2/auth/login",
            data={"username": self.username, "password": self.password},
        )
        login.raise_for_status()
        if login.status_code == 204:
            return
        if login.text.strip() != "Ok.":
            raise QBittorrentAuthError("qBittorrent rejected the configured username or password.")

    async def _configure_preferences(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            f"{self.rpc_url}/api/v2/app/setPreferences",
            data={
                "json": json.dumps(
                    {
                        "listen_port": self.listen_port,
                        "dht": True,
                        "pex": True,
                        "lsd": True,
                        "upnp": True,
                        "random_port": False,
                    }
                )
            },
        )
        response.raise_for_status()


async def check_qbittorrent(settings: object) -> None:
    downloader = QBittorrentDownloader.from_settings(settings)
    await downloader.check()
