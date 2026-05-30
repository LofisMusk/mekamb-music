import unittest
from dataclasses import dataclass

from app.sources.personal_1337x import (
    MissingTorrentMetadata,
    OwnershipMismatch,
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


class Personal1337xProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_returns_only_configured_uploader(self):
        client = FakeClient(
            [
                FakeItem("mine", "1", "mekamb"),
                FakeItem("not mine", "2", "other"),
            ],
            FakeItem("mine", "1", "mekamb"),
        )
        provider = Personal1337xProvider(uploader="mekamb", client=client)

        results = await provider.search("ambient")

        self.assertEqual([item.torrent_id for item in results], ["1"])
        self.assertEqual(client.search_kwargs["category"].lower(), "music")

    async def test_import_rechecks_info_uploader(self):
        client = FakeClient([], FakeItem("not mine", "1", "other"))
        provider = Personal1337xProvider(uploader="mekamb", client=client)

        with self.assertRaises(OwnershipMismatch):
            await provider.resolve_for_import("1")

    async def test_import_rejects_missing_magnet_or_hash(self):
        provider = Personal1337xProvider(
            uploader="mekamb",
            client=FakeClient([], FakeItem("mine", "1", "mekamb", magnet_link="", info_hash="ABC")),
        )
        with self.assertRaises(MissingTorrentMetadata):
            await provider.resolve_for_import("1")

        provider = Personal1337xProvider(
            uploader="mekamb",
            client=FakeClient([], FakeItem("mine", "1", "mekamb", magnet_link="magnet:", info_hash="")),
        )
        with self.assertRaises(MissingTorrentMetadata):
            await provider.resolve_for_import("1")


if __name__ == "__main__":
    unittest.main()
