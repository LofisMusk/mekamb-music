import unittest

from app.catalog.lidarr_client import LidarrClient, LidarrNotConfigured


class LidarrClientTests(unittest.TestCase):
    def test_unconfigured_client_reports_not_configured(self):
        client = LidarrClient(base_url="", api_key="")
        self.assertFalse(client.configured)
        with self.assertRaises(LidarrNotConfigured):
            client.system_status()

    def test_lookup_empty_term_returns_empty_without_request(self):
        client = LidarrClient(base_url="http://lidarr:8686", api_key="k")
        self.assertEqual(client.lookup("artist", "   "), [])

    def test_add_artist_builds_expected_body(self):
        client = LidarrClient(
            base_url="http://lidarr:8686",
            api_key="k",
            root_folder="/music",
            quality_profile_id=3,
            metadata_profile_id=2,
        )
        calls = []

        def fake_request(method, path, *, query=None, body=None):
            calls.append((method, path, body))
            return {"id": 1}

        client._request = fake_request  # type: ignore[assignment]
        client.add_artist(foreign_artist_id="mbid-1", artist_name="Boards of Canada")

        method, path, body = calls[0]
        self.assertEqual((method, path), ("POST", "/api/v1/artist"))
        self.assertEqual(body["foreignArtistId"], "mbid-1")
        self.assertEqual(body["rootFolderPath"], "/music")
        self.assertEqual(body["qualityProfileId"], 3)
        self.assertTrue(body["monitored"])
        self.assertTrue(body["addOptions"]["searchForMissingAlbums"])

    def test_add_album_includes_embedded_artist(self):
        client = LidarrClient(base_url="http://lidarr:8686", api_key="k", root_folder="/music")
        calls = []
        client._request = lambda method, path, *, query=None, body=None: calls.append((method, path, body)) or {}  # type: ignore[assignment]

        client.add_album(
            foreign_album_id="album-1",
            album_title="Geogaddi",
            foreign_artist_id="artist-1",
            artist_name="Boards of Canada",
        )
        method, path, body = calls[0]
        self.assertEqual((method, path), ("POST", "/api/v1/album"))
        self.assertEqual(body["foreignAlbumId"], "album-1")
        self.assertEqual(body["artist"]["foreignArtistId"], "artist-1")
        self.assertTrue(body["addOptions"]["searchForNewAlbum"])


if __name__ == "__main__":
    unittest.main()
