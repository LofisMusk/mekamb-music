from datetime import UTC, datetime

import pytest

from app.sources.personal_1337x import SourceBlockedError
from app.sources.piratebay import PirateBaySearchResult
from app.sources.search import UnifiedTorrentSearch, music_query_variants


class FakePirateBayProvider:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search(self, query: str):
        self.queries.append(query)
        return [
            PirateBaySearchResult(
                name="Daft Punk - Discovery",
                torrent_id="pb-1",
                info_hash="ABC",
                magnet_link="magnet:?xt=urn:btih:ABC",
                url="https://example.test/pb-1",
                seeders="42",
                leechers="2",
                size_bytes=1234,
                num_files=14,
                uploader="Anonymous",
                category="101",
                status="vip",
                added_at=None,
                discovered_at=datetime.now(UTC),
            )
        ]


class Blocked1337xProvider:
    async def search(
        self,
        query: str,
        *,
        page: int = 1,
        sort_by: str | None = None,
        redis=None,
    ):
        raise SourceBlockedError("Cloudflare challenge")


def test_music_query_variants_strip_release_noise():
    assert music_query_variants("Daft Punk - Discovery [FLAC 2001]") == [
        "Daft Punk - Discovery [FLAC 2001]",
        "Daft Punk - Discovery",
        "Daft Punk Discovery",
    ]


@pytest.mark.asyncio
async def test_unified_search_keeps_results_when_1337x_is_blocked():
    piratebay = FakePirateBayProvider()
    search = UnifiedTorrentSearch(
        piratebay=piratebay,
        personal_1337x=Blocked1337xProvider(),
    )

    results = await search.search("Daft Punk - Discovery [FLAC 2001]")

    assert [item.source for item in results] == ["piratebay"]
    assert [item.torrent_id for item in results] == ["pb-1"]
    assert piratebay.queries == [
        "Daft Punk - Discovery [FLAC 2001]",
        "Daft Punk - Discovery",
        "Daft Punk Discovery",
    ]
