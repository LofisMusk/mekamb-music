from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.deps import internet_archive_client
from app.catalog.internet_archive import InternetArchiveError, InternetArchiveRelease
from app.core.config import settings
from app.main import app


def _release(**overrides):
    defaults = dict(
        identifier="taco-hemingway-cafe-belga",
        title="Taco Hemingway – Café Belga",
        size_bytes=123456,
        downloads=42,
        published_at=datetime(2019, 5, 1, tzinfo=timezone.utc),
        torrent_url="https://archive.org/download/x/x_archive.torrent",
    )
    defaults.update(overrides)
    return InternetArchiveRelease(**defaults)


class FakeClient:
    def __init__(self, releases=None, error=None):
        self._releases = releases or []
        self._error = error

    async def search(self, query, *, rows=100):
        if self._error:
            raise self._error
        return self._releases


def test_caps_returns_xml_without_hitting_client():
    app.dependency_overrides[internet_archive_client] = lambda: FakeClient()
    try:
        response = TestClient(app).get("/torznab/internetarchive/api?t=caps")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert b"<caps>" in response.content


def test_search_returns_torznab_items():
    app.dependency_overrides[internet_archive_client] = lambda: FakeClient(releases=[_release()])
    try:
        response = TestClient(app).get("/torznab/internetarchive/api?t=search&q=Taco+Hemingway")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert b"<title>Taco Hemingway" in response.content
    assert b"archive_archive.torrent" not in response.content
    assert b"x_archive.torrent" in response.content
    assert b'torznab:attr name="seeders" value="1"' in response.content


def test_search_returns_empty_feed_instead_of_error_on_upstream_failure():
    app.dependency_overrides[internet_archive_client] = lambda: FakeClient(
        error=InternetArchiveError("archive.org is slow")
    )
    try:
        response = TestClient(app).get("/torznab/internetarchive/api?t=search&q=x")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert b"<item>" not in response.content


def test_invalid_apikey_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "torznab_ia_api_key", "secret")
    app.dependency_overrides[internet_archive_client] = lambda: FakeClient()
    try:
        response = TestClient(app).get("/torznab/internetarchive/api?t=caps&apikey=wrong")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


def test_valid_apikey_is_accepted(monkeypatch):
    monkeypatch.setattr(settings, "torznab_ia_api_key", "secret")
    app.dependency_overrides[internet_archive_client] = lambda: FakeClient()
    try:
        response = TestClient(app).get("/torznab/internetarchive/api?t=caps&apikey=secret")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
