from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.deps import (
    music_indexer_provider,
    personal_1337x_provider,
    piratebay_provider,
    require_token,
)
from app.main import app
from app.sources.indexers import MusicIndexerSearchResult
from app.sources.personal_1337x import Personal1337xSearchResult
from app.sources.piratebay import PirateBaySearchResult


class FakeProvider:
    async def search(self, q: str, *, page: int = 1, sort_by: str | None = None, redis=None):
        assert q == "ambient"
        assert page == 1
        assert sort_by == "seeders"
        return [
            Personal1337xSearchResult(
                name="mine",
                torrent_id="1",
                url="https://1337x.to/torrent/1/mine/",
                seeders="10",
                leechers="0",
                size="100 MB",
                time="today",
                uploader="mekamb",
                uploader_link="/user/mekamb/",
                discovered_at=datetime.now(UTC),
            )
        ]


class FakePirateBayProvider:
    async def search(self, q: str):
        assert q == "ambient"
        return [
            PirateBaySearchResult(
                name="ambient record",
                torrent_id="pb-1",
                info_hash="ABC",
                magnet_link="magnet:?xt=urn:btih:ABC",
                url="https://example.test/pb-1",
                seeders="50",
                leechers="1",
                size_bytes=1234,
                num_files=1,
                uploader="Anonymous",
                category="101",
                status="vip",
                added_at=None,
                discovered_at=datetime.now(UTC),
            )
        ]


class FakeMusicIndexerProvider:
    def __init__(self) -> None:
        self.api_key = ""

    def with_api_key(self, api_key: str | None):
        self.api_key = api_key or ""
        return self

    async def search(self, q: str):
        assert q == "ambient"
        return [
            MusicIndexerSearchResult(
                source="indexer",
                name="ambient indexer record",
                torrent_id="ABC123",
                info_hash="ABC123",
                magnet_link="magnet:?xt=urn:btih:ABC123",
                url="https://indexer.example/details/1",
                seeders="60",
                leechers="3",
                size_bytes=1234,
                uploader="indexer",
                discovered_at=datetime.now(UTC),
            )
        ]


def test_search_endpoint_returns_provider_results():
    app.dependency_overrides[require_token] = lambda: None
    app.dependency_overrides[personal_1337x_provider] = lambda: FakeProvider()
    try:
        response = TestClient(app).get("/sources/1337x/search?q=ambient")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert [item["torrent_id"] for item in payload["items"]] == ["1"]


def test_unified_search_endpoint_returns_source_tagged_results():
    app.dependency_overrides[require_token] = lambda: None
    app.dependency_overrides[personal_1337x_provider] = lambda: FakeProvider()
    app.dependency_overrides[piratebay_provider] = lambda: FakePirateBayProvider()
    try:
        response = TestClient(app).get("/sources/search?q=ambient")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert [(item["source"], item["torrent_id"]) for item in payload["items"]] == [
        ("piratebay", "pb-1"),
        ("1337x", "1"),
    ]


def test_indexer_search_endpoint_returns_importable_results():
    provider = FakeMusicIndexerProvider()
    app.dependency_overrides[require_token] = lambda: None
    app.dependency_overrides[music_indexer_provider] = lambda: provider
    try:
        response = TestClient(app).get(
            "/sources/indexers/search?q=ambient",
            headers={"X-Prowlarr-Api-Key": "device-key"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["source"] == "indexer"
    assert payload["items"][0]["info_hash"] == "ABC123"
    assert payload["items"][0]["magnet_link"].startswith("magnet:")
    assert provider.api_key == "device-key"
