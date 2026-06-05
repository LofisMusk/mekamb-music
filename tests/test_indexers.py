from app.sources.indexers import MusicIndexerProvider


class FakeMusicIndexerProvider(MusicIndexerProvider):
    def __init__(self, payload: str):
        super().__init__(torznab_urls=["https://prowlarr.example/torznab/music"])
        self.payload = payload
        self.queries: list[str] = []

    def _fetch_torznab(self, base_url: str, query: str) -> str:
        self.queries.append(query)
        return self.payload


class FakeProwlarrProvider(MusicIndexerProvider):
    def __init__(self, payload):
        super().__init__(prowlarr_url="http://prowlarr:9696", api_key="secret")
        self.payload = payload
        self.queries: list[str] = []

    def _fetch_prowlarr(self, query: str):
        self.queries.append(query)
        return self.payload


async def test_music_indexer_search_parses_torznab_magnet_results():
    provider = FakeMusicIndexerProvider(
        """<?xml version="1.0" encoding="UTF-8"?>
        <rss xmlns:torznab="http://torznab.com/schemas/2015/feed">
          <channel>
            <item>
              <title>Daft Punk - Discovery FLAC</title>
              <guid>https://indexer.example/details/1</guid>
              <size>1234</size>
              <torznab:attr name="seeders" value="44" />
              <torznab:attr name="leechers" value="2" />
              <torznab:attr name="infohash" value="ABC123" />
              <torznab:attr name="magneturl" value="magnet:?xt=urn:btih:ABC123&amp;dn=Discovery" />
            </item>
          </channel>
        </rss>
        """
    )

    results = await provider.search("Daft Punk Discovery")

    assert provider.queries == ["Daft Punk Discovery"]
    assert len(results) == 1
    assert results[0].source == "indexer"
    assert results[0].torrent_id == "ABC123"
    assert results[0].magnet_link.startswith("magnet:")
    assert results[0].seeders == "44"


async def test_music_indexer_search_parses_prowlarr_api_results():
    provider = FakeProwlarrProvider(
        [
            {
                "title": "Daft Punk - Discovery FLAC",
                "infoHash": "ABC123",
                "magnetUrl": "magnet:?xt=urn:btih:ABC123&dn=Discovery",
                "infoUrl": "https://indexer.example/details/1",
                "seeders": 44,
                "leechers": 2,
                "size": 1234,
                "indexer": "Prowlarr Indexer",
            }
        ]
    )

    results = await provider.search("Daft Punk Discovery")

    assert provider.queries == ["Daft Punk Discovery"]
    assert len(results) == 1
    assert results[0].source == "indexer"
    assert results[0].torrent_id == "ABC123"
    assert results[0].uploader == "Prowlarr Indexer"


async def test_music_indexer_candidate_from_payload_accepts_selected_result():
    provider = MusicIndexerProvider()

    candidate = provider.candidate_from_payload(
        {
            "name": "Daft Punk - Discovery FLAC",
            "torrent_id": "ABC123",
            "info_hash": "ABC123",
            "magnet_link": "magnet:?xt=urn:btih:ABC123&dn=Discovery",
            "uploader": "indexer",
            "source_url": "https://indexer.example/details/1",
        }
    )

    assert candidate.info_hash == "ABC123"
    assert candidate.magnet_link.startswith("magnet:")
    assert candidate.source_url == "https://indexer.example/details/1"


def test_music_indexer_with_api_key_overrides_configured_key():
    provider = MusicIndexerProvider(
        prowlarr_url="http://prowlarr:9696",
        api_key="env-key",
        categories=["3000"],
    )

    override = provider.with_api_key("device-key")

    assert override.api_key == "device-key"
    assert override.prowlarr_url == provider.prowlarr_url
    assert override.categories == provider.categories


def test_music_indexer_with_blank_api_key_keeps_configured_key():
    provider = MusicIndexerProvider(
        prowlarr_url="http://prowlarr:9696",
        api_key="env-key",
        categories=["3000"],
    )

    assert provider.with_api_key("").api_key == "env-key"
