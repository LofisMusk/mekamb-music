from datetime import datetime, timezone

import httpx
import pytest

from app.catalog.internet_archive import InternetArchiveClient, InternetArchiveError, _parse_docs


def _doc(**overrides):
    doc = {
        "identifier": "taco-hemingway-cafe-belga",
        "title": "Taco Hemingway – Café Belga",
        "item_size": 123456,
        "downloads": 42,
        "btih": "abc123",
        "publicdate": "2019-05-01T00:00:00Z",
    }
    doc.update(overrides)
    return doc


def test_parse_docs_skips_entries_without_btih():
    docs = [_doc(btih=""), _doc(identifier="second")]
    releases = _parse_docs(docs)
    assert len(releases) == 1
    assert releases[0].identifier == "second"


def test_parse_docs_builds_direct_torrent_url():
    releases = _parse_docs([_doc()])
    assert releases[0].torrent_url == (
        "https://archive.org/download/taco-hemingway-cafe-belga/"
        "taco-hemingway-cafe-belga_archive.torrent"
    )
    assert releases[0].published_at == datetime(2019, 5, 1, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_search_retries_on_timeout_then_succeeds(monkeypatch):
    client = InternetArchiveClient(redis_url="redis://localhost:6379/0", max_attempts=2)

    calls = {"count": 0}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"response": {"docs": [_doc()]}}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None):
            calls["count"] += 1
            if calls["count"] == 1:
                raise httpx.TimeoutException("timed out")
            return FakeResponse()

    async def fake_get(self, key):
        return None

    async def fake_set(self, key, value, ex=None):
        return None

    async def fake_sleep(seconds):
        return None

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(client._redis, "get", fake_get.__get__(client._redis))
    monkeypatch.setattr(client._redis, "set", fake_set.__get__(client._redis))
    monkeypatch.setattr("app.catalog.internet_archive.asyncio.sleep", fake_sleep)

    releases = await client.search("Taco Hemingway")
    assert calls["count"] == 2
    assert len(releases) == 1
    assert releases[0].identifier == "taco-hemingway-cafe-belga"


@pytest.mark.asyncio
async def test_search_raises_after_exhausting_retries(monkeypatch):
    client = InternetArchiveClient(redis_url="redis://localhost:6379/0", max_attempts=2)

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None):
            raise httpx.TimeoutException("timed out")

    async def fake_get(self, key):
        return None

    async def fake_sleep(seconds):
        return None

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(client._redis, "get", fake_get.__get__(client._redis))
    monkeypatch.setattr("app.catalog.internet_archive.asyncio.sleep", fake_sleep)

    with pytest.raises(InternetArchiveError):
        await client.search("Taco Hemingway")


@pytest.mark.asyncio
async def test_search_uses_cache_without_hitting_network(monkeypatch):
    client = InternetArchiveClient(redis_url="redis://localhost:6379/0")

    import json

    async def fake_get(self, key):
        return json.dumps([_doc()])

    def fail_if_called(*args, **kwargs):
        raise AssertionError("should not hit the network when cache has a value")

    monkeypatch.setattr(client._redis, "get", fake_get.__get__(client._redis))
    monkeypatch.setattr(httpx, "AsyncClient", fail_if_called)

    releases = await client.search("Taco Hemingway")
    assert len(releases) == 1
