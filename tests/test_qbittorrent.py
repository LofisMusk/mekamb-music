from pathlib import Path

import httpx
import pytest

from app.downloads.qbittorrent import QBittorrentAuthError, QBittorrentDownloader, QBittorrentError
from app.downloads.domain import TorrentRuntimeStatus


def test_torrent_runtime_status_completion_policy():
    assert TorrentRuntimeStatus(
        name="done",
        info_hash="ABC123",
        state="uploading",
        progress=0.99,
        size_bytes=100,
        downloaded_bytes=100,
        download_speed_bytes=0,
        eta_seconds=0,
        save_path="/downloads/incomplete/import-id",
    ).is_complete
    assert not TorrentRuntimeStatus(
        name="partial",
        info_hash="ABC123",
        state="downloading",
        progress=0.99,
        size_bytes=100,
        downloaded_bytes=99,
        download_speed_bytes=1,
        eta_seconds=10,
        save_path="/downloads/incomplete/import-id",
    ).is_complete


@pytest.mark.asyncio
async def test_qbittorrent_status_reads_torrent_by_label():
    seen_paths = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        if request.url.path == "/api/v2/auth/login":
            return httpx.Response(200, text="Ok.")
        if request.url.path == "/api/v2/app/setPreferences":
            assert "listen_port" in request.content.decode()
            return httpx.Response(200)
        if request.url.path == "/api/v2/torrents/info":
            assert request.url.params["tag"] == "mekamb-music:import-id"
            return httpx.Response(
                200,
                json=[
                    {
                        "name": "track.flac",
                        "hash": "ABC123",
                        "state": "downloading",
                        "progress": 0.5,
                        "size": 1000,
                        "downloaded": 500,
                        "dlspeed": 25,
                        "eta": 20,
                        "save_path": "/downloads/incomplete/import-id",
                    }
                ],
            )
        return httpx.Response(404)

    downloader = QBittorrentDownloader(
        rpc_url="http://qbittorrent:8080",
        username="admin",
        password="adminadmin",
        transport=httpx.MockTransport(handler),
    )

    status = await downloader.status_by_label("mekamb-music:import-id")

    assert seen_paths == [
        "/api/v2/auth/login",
        "/api/v2/app/setPreferences",
        "/api/v2/torrents/info",
    ]
    assert status is not None
    assert status.name == "track.flac"
    assert status.info_hash == "ABC123"
    assert status.progress == 0.5


@pytest.mark.asyncio
async def test_qbittorrent_status_returns_none_when_tag_not_found():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/auth/login":
            return httpx.Response(200, text="Ok.")
        if request.url.path == "/api/v2/app/setPreferences":
            return httpx.Response(200)
        if request.url.path == "/api/v2/torrents/info":
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    downloader = QBittorrentDownloader(
        rpc_url="http://qbittorrent:8080",
        username="admin",
        password="adminadmin",
        transport=httpx.MockTransport(handler),
    )

    assert await downloader.status_by_label("missing") is None


@pytest.mark.asyncio
async def test_qbittorrent_status_rejects_unexpected_payload():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/auth/login":
            return httpx.Response(200, text="Ok.")
        if request.url.path == "/api/v2/app/setPreferences":
            return httpx.Response(200)
        if request.url.path == "/api/v2/torrents/info":
            return httpx.Response(200, json={"not": "a list"})
        return httpx.Response(404)

    downloader = QBittorrentDownloader(
        rpc_url="http://qbittorrent:8080",
        username="admin",
        password="adminadmin",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(QBittorrentError):
        await downloader.status_by_label("bad")


@pytest.mark.asyncio
async def test_qbittorrent_accepts_no_content_login_response():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/v2/auth/login":
            return httpx.Response(204)
        if request.url.path == "/api/v2/app/setPreferences":
            return httpx.Response(200)
        if request.url.path == "/api/v2/torrents/info":
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    downloader = QBittorrentDownloader(
        rpc_url="http://qbittorrent:8080",
        username="admin",
        password="strong-password",
        transport=httpx.MockTransport(handler),
    )

    assert await downloader.status_by_label("missing") is None
    assert [request.url.path for request in requests] == [
        "/api/v2/auth/login",
        "/api/v2/app/setPreferences",
        "/api/v2/torrents/info",
    ]


@pytest.mark.asyncio
async def test_qbittorrent_rejects_failed_login_even_when_http_status_is_200():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/v2/auth/login":
            return httpx.Response(200, text="Fails.")
        if request.url.path == "/api/v2/torrents/info":
            raise AssertionError("torrent info should not be requested after failed login")
        return httpx.Response(404)

    downloader = QBittorrentDownloader(
        rpc_url="http://qbittorrent:8080",
        username="admin",
        password="wrong",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(QBittorrentAuthError):
        await downloader.status_by_label("mekamb-music:import-id")

    assert [request.url.path for request in requests] == ["/api/v2/auth/login"]


@pytest.mark.asyncio
async def test_qbittorrent_enqueue_sends_magnet_to_quarantine_path():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/v2/auth/login":
            return httpx.Response(200, text="Ok.")
        if request.url.path == "/api/v2/app/setPreferences":
            return httpx.Response(200)
        if request.url.path == "/api/v2/torrents/add":
            body = request.content.decode()
            assert "magnet%3A%3Fxt%3Durn%3Abtih%3AABC123" in body
            assert "%2Fdownloads%2Fincomplete%2Fimport-id" in body
            assert "mekamb-music%3Aimport-id" in body
            assert "ratioLimit=0" in body
            assert "seedingTimeLimit=0" in body
            return httpx.Response(200, text="Ok.")
        return httpx.Response(404)

    downloader = QBittorrentDownloader(
        rpc_url="http://qbittorrent:8080",
        username="admin",
        password="adminadmin",
        transport=httpx.MockTransport(handler),
    )

    await downloader.enqueue(
        magnet_link="magnet:?xt=urn:btih:ABC123",
        download_path=Path("/downloads/incomplete/import-id"),
        label="mekamb-music:import-id",
    )

    assert [request.url.path for request in requests] == [
        "/api/v2/auth/login",
        "/api/v2/app/setPreferences",
        "/api/v2/torrents/add",
    ]


@pytest.mark.asyncio
async def test_qbittorrent_delete_by_label_removes_matching_hashes():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/v2/auth/login":
            return httpx.Response(200, text="Ok.")
        if request.url.path == "/api/v2/torrents/info":
            assert request.url.params["tag"] == "mekamb-music:import-id"
            return httpx.Response(200, json=[{"hash": "ABC123"}, {"hash": "DEF456"}])
        if request.url.path == "/api/v2/torrents/delete":
            body = request.content.decode()
            assert "hashes=ABC123%7CDEF456" in body
            assert "deleteFiles=true" in body
            return httpx.Response(200, text="Ok.")
        return httpx.Response(404)

    downloader = QBittorrentDownloader(
        rpc_url="http://qbittorrent:8080",
        username="admin",
        password="adminadmin",
        transport=httpx.MockTransport(handler),
    )

    removed = await downloader.delete_by_label("mekamb-music:import-id", delete_files=True)

    assert removed
    assert [request.url.path for request in requests] == [
        "/api/v2/auth/login",
        "/api/v2/torrents/info",
        "/api/v2/torrents/delete",
    ]


@pytest.mark.asyncio
async def test_qbittorrent_delete_by_label_returns_false_when_tag_not_found():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/auth/login":
            return httpx.Response(200, text="Ok.")
        if request.url.path == "/api/v2/torrents/info":
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    downloader = QBittorrentDownloader(
        rpc_url="http://qbittorrent:8080",
        username="admin",
        password="adminadmin",
        transport=httpx.MockTransport(handler),
    )

    assert not await downloader.delete_by_label("missing", delete_files=True)
