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


class NullRedisPatch:
    """Patches a client's redis get/set to a no-op in-memory store so tests don't
    need a real Redis connection."""

    def __init__(self, monkeypatch, redis):
        self.store: dict[str, str] = {}

        async def fake_get(_self, key):
            return self.store.get(key)

        async def fake_set(_self, key, value, ex=None):
            self.store[key] = value

        monkeypatch.setattr(redis, "get", fake_get.__get__(redis))
        monkeypatch.setattr(redis, "set", fake_set.__get__(redis))


class FakeAsyncClient:
    """Routes by URL: the search endpoint vs. the per-item metadata endpoint."""

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None):
        if "advancedsearch" in url:
            return _FakeResponse(self.search_payload())
        return _FakeResponse(self.metadata_payload())

    def search_payload(self):
        return {"response": {"docs": [_doc()]}}

    def metadata_payload(self):
        return {
            "files": [
                {"name": "01 Song.mp3", "size": "1000000"},
                {"name": "02 Song.mp3", "size": "2000000"},
                {"name": "cover.png", "size": "50000"},
                {"name": "spectrogram.png", "size": "80000"},
            ]
        }


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


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
    NullRedisPatch(monkeypatch, client._redis)

    calls = {"search": 0}

    class FlakySearchClient(FakeAsyncClient):
        async def get(self, url, params=None):
            if "advancedsearch" in url:
                calls["search"] += 1
                if calls["search"] == 1:
                    raise httpx.TimeoutException("timed out")
            return await super().get(url, params=params)

    async def fake_sleep(seconds):
        return None

    monkeypatch.setattr(httpx, "AsyncClient", FlakySearchClient)
    monkeypatch.setattr("app.catalog.internet_archive.asyncio.sleep", fake_sleep)

    releases = await client.search("Taco Hemingway")
    assert calls["search"] == 2
    assert len(releases) == 1
    assert releases[0].identifier == "taco-hemingway-cafe-belga"


@pytest.mark.asyncio
async def test_search_raises_after_exhausting_retries(monkeypatch):
    client = InternetArchiveClient(redis_url="redis://localhost:6379/0", max_attempts=2)
    NullRedisPatch(monkeypatch, client._redis)

    class AlwaysTimesOut:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None):
            raise httpx.TimeoutException("timed out")

    async def fake_sleep(seconds):
        return None

    monkeypatch.setattr(httpx, "AsyncClient", AlwaysTimesOut)
    monkeypatch.setattr("app.catalog.internet_archive.asyncio.sleep", fake_sleep)

    with pytest.raises(InternetArchiveError):
        await client.search("Taco Hemingway")


@pytest.mark.asyncio
async def test_search_uses_cache_without_refetching_search_results(monkeypatch):
    client = InternetArchiveClient(redis_url="redis://localhost:6379/0")
    redis_patch = NullRedisPatch(monkeypatch, client._redis)

    calls = {"search": 0}

    class CountingClient(FakeAsyncClient):
        async def get(self, url, params=None):
            if "advancedsearch" in url:
                calls["search"] += 1
            return await super().get(url, params=params)

    monkeypatch.setattr(httpx, "AsyncClient", CountingClient)

    await client.search("Taco Hemingway")
    await client.search("Taco Hemingway")
    assert calls["search"] == 1
    assert len(redis_patch.store) >= 1


@pytest.mark.asyncio
async def test_search_replaces_size_with_audio_only_total(monkeypatch):
    client = InternetArchiveClient(redis_url="redis://localhost:6379/0")
    NullRedisPatch(monkeypatch, client._redis)

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    releases = await client.search("Taco Hemingway")
    assert len(releases) == 1
    # sum of the two .mp3 files only, excluding cover.png / spectrogram.png
    assert releases[0].size_bytes == 3_000_000


@pytest.mark.asyncio
async def test_search_keeps_original_size_when_metadata_fetch_fails(monkeypatch):
    client = InternetArchiveClient(redis_url="redis://localhost:6379/0")
    NullRedisPatch(monkeypatch, client._redis)

    class MetadataFailsClient(FakeAsyncClient):
        async def get(self, url, params=None):
            if "advancedsearch" in url:
                return _FakeResponse(self.search_payload())
            raise httpx.TimeoutException("metadata timed out")

    monkeypatch.setattr(httpx, "AsyncClient", MetadataFailsClient)

    releases = await client.search("Taco Hemingway")
    assert len(releases) == 1
    assert releases[0].size_bytes == 123456  # falls back to the original item_size
