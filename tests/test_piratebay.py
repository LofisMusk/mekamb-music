from datetime import UTC, datetime

import pytest

from app.sources.piratebay import PirateBayMarkerMismatch, PirateBayProvider


class FakePirateBayProvider(PirateBayProvider):
    def __init__(self, payload):
        super().__init__(title_marker="[PMEDIA]")
        self.payload = payload

    def _get_json(self, path: str, **params: str):
        return self.payload

@pytest.mark.asyncio
async def test_piratebay_search_filters_to_pmedia_titles_async():
    provider = FakePirateBayProvider(
        [
            {
                "id": "1",
                "name": "Mekamb - Private Album [PMEDIA]",
                "info_hash": "ABC123",
                "seeders": "10",
                "leechers": "1",
                "size": "1234",
                "num_files": "2",
                "username": "Anonymous",
                "added": "1731612447",
                "status": "vip",
                "category": "104",
            },
            {
                "id": "2",
                "name": "Other Album",
                "info_hash": "DEF456",
                "seeders": "20",
            },
        ]
    )

    results = await provider.search("mekamb")

    assert len(results) == 1
    assert results[0].torrent_id == "1"
    assert results[0].uploader == "Anonymous"
    assert results[0].size_bytes == 1234
    assert results[0].added_at == datetime.fromtimestamp(1731612447, tz=UTC)
    assert results[0].magnet_link.startswith("magnet:?xt=urn:btih:ABC123")


@pytest.mark.asyncio
async def test_piratebay_import_rejects_titles_without_marker():
    provider = FakePirateBayProvider(
        {
            "id": "2",
            "name": "Other Album",
            "info_hash": "DEF456",
            "username": "Anonymous",
        }
    )

    with pytest.raises(PirateBayMarkerMismatch):
        await provider.resolve_for_import("2")
