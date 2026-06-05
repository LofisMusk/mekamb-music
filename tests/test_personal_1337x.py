import unittest
from dataclasses import dataclass
from unittest.mock import patch

from app.sources.personal_1337x import (
    MissingTorrentMetadata,
    Personal1337xProvider,
)


@dataclass
class FakeItem:
    name: str
    torrent_id: str
    uploader: str
    magnet_link: str = "magnet:?xt=urn:btih:abc"
    info_hash: str = "ABC"
    url: str = "https://1337x.to/torrent/1/example/"
    seeders: str = "10"
    leechers: str = "0"
    size: str = "10 MB"
    time: str = "today"
    uploader_link: str = "/user/mekamb/"


class FakeResult:
    def __init__(self, items):
        self.items = items


class FakeClient:
    base_url = "https://1337x.to"

    def __init__(self, search_items, info_item):
        self.search_items = search_items
        self.info_item = info_item

    def search(self, *args, **kwargs):
        self.search_kwargs = kwargs
        return FakeResult(self.search_items)

    def info(self, *args, **kwargs):
        self.info_kwargs = kwargs
        return self.info_item


class FailingSearchClient(FakeClient):
    def search(self, *args, **kwargs):
        raise RuntimeError("blocked")


class FailingInfoClient(FakeClient):
    def info(self, *args, **kwargs):
        raise RuntimeError("blocked")


class Personal1337xProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_returns_all_music_results(self):
        client = FakeClient(
            [
                FakeItem("mine", "1", "mekamb"),
                FakeItem("not mine", "2", "other"),
            ],
            FakeItem("mine", "1", "mekamb"),
        )
        provider = Personal1337xProvider(client=client)

        results = await provider.search("ambient")

        self.assertEqual([item.torrent_id for item in results], ["1", "2"])
        self.assertEqual(client.search_kwargs["category"].lower(), "music")

    async def test_search_falls_back_to_next_mirror(self):
        clients = {
            "https://blocked.example": FailingSearchClient([], FakeItem("mine", "1", "mekamb")),
            "https://mirror.example": FakeClient(
                [FakeItem("mine", "1", "mekamb")],
                FakeItem("mine", "1", "mekamb"),
            ),
        }
        with patch(
            "app.sources.personal_1337x._build_default_client",
            side_effect=lambda base_url: clients[base_url],
        ):
            provider = Personal1337xProvider(
                base_urls=["https://blocked.example", "https://mirror.example"]
            )
            results = await provider.search("ambient")

        self.assertEqual([item.torrent_id for item in results], ["1"])
        self.assertEqual(clients["https://mirror.example"].search_kwargs["category"].lower(), "music")

    async def test_import_accepts_any_uploader(self):
        client = FakeClient([], FakeItem("not mine", "1", "other"))
        provider = Personal1337xProvider(client=client)

        candidate = await provider.resolve_for_import("1")

        self.assertEqual(candidate.uploader, "other")

    async def test_import_falls_back_to_next_mirror(self):
        clients = {
            "https://blocked.example": FailingInfoClient([], FakeItem("mine", "1", "mekamb")),
            "https://mirror.example": FakeClient([], FakeItem("mine", "1", "mekamb")),
        }
        with patch(
            "app.sources.personal_1337x._build_default_client",
            side_effect=lambda base_url: clients[base_url],
        ):
            provider = Personal1337xProvider(
                base_urls=["https://blocked.example", "https://mirror.example"]
            )
            candidate = await provider.resolve_for_import("1")

        self.assertEqual(candidate.info_hash, "ABC")
        self.assertEqual(clients["https://mirror.example"].info_kwargs["torrent_id"], "1")

    async def test_import_rejects_missing_magnet_or_hash(self):
        provider = Personal1337xProvider(
            client=FakeClient([], FakeItem("mine", "1", "mekamb", magnet_link="", info_hash="ABC")),
        )
        with self.assertRaises(MissingTorrentMetadata):
            await provider.resolve_for_import("1")

        provider = Personal1337xProvider(
            client=FakeClient([], FakeItem("mine", "1", "mekamb", magnet_link="magnet:", info_hash="")),
        )
        with self.assertRaises(MissingTorrentMetadata):
            await provider.resolve_for_import("1")


if __name__ == "__main__":
    unittest.main()
