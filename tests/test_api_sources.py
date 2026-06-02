from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.deps import personal_1337x_provider, require_token
from app.main import app
from app.sources.personal_1337x import Personal1337xSearchResult


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
