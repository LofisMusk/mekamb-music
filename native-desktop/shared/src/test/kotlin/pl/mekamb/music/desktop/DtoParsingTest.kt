package pl.mekamb.music.desktop

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import pl.mekamb.music.desktop.api.DownloadStatusResponse
import pl.mekamb.music.desktop.api.GhRelease
import pl.mekamb.music.desktop.api.PersonalizedHomeResponse
import pl.mekamb.music.desktop.api.SourceSearchResponse
import pl.mekamb.music.desktop.api.TrackListResponse
import pl.mekamb.music.desktop.api.apiJson

class DtoParsingTest {

    @Test
    fun `parses TrackListResponse with snake_case keys`() {
        val json = """
            {
              "items": [
                {
                  "id": "trk-1",
                  "title": "Midnight Drive",
                  "artist": "Neon Fields",
                  "album": "City Lights",
                  "storage_key": "tracks/trk-1.flac",
                  "original_filename": "01 Midnight Drive.flac",
                  "media_type": "audio/flac",
                  "codec": "flac",
                  "duration_seconds": 245.7,
                  "size_bytes": 31457280,
                  "cover_key": "covers/trk-1.jpg",
                  "source_import_id": "imp-9",
                  "created_at": "2026-06-01T10:00:00Z",
                  "last_accessed": "2026-07-01T12:00:00Z"
                },
                {
                  "id": "trk-2",
                  "title": "Untitled"
                }
              ],
              "limit": 200,
              "offset": 0
            }
        """.trimIndent()

        val parsed = apiJson.decodeFromString<TrackListResponse>(json)
        assertEquals(2, parsed.items.size)
        assertEquals(200, parsed.limit)
        assertEquals(0, parsed.offset)

        val first = parsed.items[0]
        assertEquals("trk-1", first.id)
        assertEquals("tracks/trk-1.flac", first.storageKey)
        assertEquals("01 Midnight Drive.flac", first.originalFilename)
        assertEquals("audio/flac", first.mediaType)
        assertEquals(245.7, first.durationSeconds)
        assertEquals(31457280L, first.sizeBytes)
        assertEquals("covers/trk-1.jpg", first.coverKey)
        assertEquals("imp-9", first.sourceImportId)

        val second = parsed.items[1]
        assertEquals("Untitled", second.title)
        assertNull(second.artist)
        assertNull(second.durationSeconds)
    }

    @Test
    fun `parses PersonalizedHomeResponse`() {
        val json = """
            {
              "recommended_tracks": [
                {
                  "track": {"id": "trk-1", "title": "Midnight Drive", "duration_seconds": 245.7},
                  "score": 0.92,
                  "reasons": ["similar to liked tracks", "recently popular"]
                }
              ],
              "daily_mixes": [
                {
                  "id": "mix-1",
                  "title": "Daily Mix 1",
                  "description": "Based on Neon Fields",
                  "seed_label": "Neon Fields",
                  "tracks": [
                    {"track": {"id": "trk-2", "title": "Second"}, "score": 0.5, "reasons": []}
                  ]
                },
                {
                  "id": "mix-2",
                  "title": "Daily Mix 2"
                }
              ]
            }
        """.trimIndent()

        val parsed = apiJson.decodeFromString<PersonalizedHomeResponse>(json)
        assertEquals(1, parsed.recommendedTracks.size)
        assertEquals("trk-1", parsed.recommendedTracks[0].track.id)
        assertEquals(0.92, parsed.recommendedTracks[0].score)
        assertEquals(2, parsed.recommendedTracks[0].reasons.size)

        assertEquals(2, parsed.dailyMixes.size)
        assertEquals("Neon Fields", parsed.dailyMixes[0].seedLabel)
        assertEquals("trk-2", parsed.dailyMixes[0].tracks[0].track.id)
        assertNull(parsed.dailyMixes[1].description)
        assertTrue(parsed.dailyMixes[1].tracks.isEmpty())
    }

    @Test
    fun `parses DownloadStatusResponse mapping import key to importRecord`() {
        val json = """
            {
              "import": {
                "id": "imp-42",
                "source": "1337x",
                "torrent_id": "999",
                "info_hash": "abcdef0123456789",
                "uploader": "uploader1",
                "source_url": "https://example.org/torrent/999",
                "status": "downloading",
                "quarantine_path": "/quarantine/imp-42",
                "error_message": null,
                "created_at": "2026-07-01T09:00:00Z",
                "updated_at": "2026-07-01T09:05:00Z"
              },
              "torrent": {
                "name": "Some Album [FLAC]",
                "info_hash": "abcdef0123456789",
                "state": "downloading",
                "progress": 0.45,
                "size_bytes": 734003200,
                "downloaded_bytes": 330301440,
                "download_speed_bytes": 5242880,
                "eta_seconds": 77,
                "save_path": "/downloads"
              }
            }
        """.trimIndent()

        val parsed = apiJson.decodeFromString<DownloadStatusResponse>(json)
        assertEquals("imp-42", parsed.importRecord.id)
        assertEquals("downloading", parsed.importRecord.status)
        assertEquals("999", parsed.importRecord.torrentId)
        assertNull(parsed.importRecord.errorMessage)

        val torrent = assertNotNull(parsed.torrent)
        assertEquals(0.45, torrent.progress)
        assertEquals(734003200L, torrent.sizeBytes)
        assertEquals(5242880L, torrent.downloadSpeedBytes)
        assertEquals(77L, torrent.etaSeconds)
    }

    @Test
    fun `parses DownloadStatusResponse without torrent`() {
        val json = """{"import": {"id": "imp-7", "status": "completed"}}"""
        val parsed = apiJson.decodeFromString<DownloadStatusResponse>(json)
        assertEquals("imp-7", parsed.importRecord.id)
        assertNull(parsed.torrent)
    }

    @Test
    fun `parses SourceSearchResponse`() {
        val json = """
            {
              "items": [
                {
                  "source": "1337x",
                  "name": "Artist - Album (2024) [FLAC]",
                  "torrent_id": "12345",
                  "info_hash": "deadbeef",
                  "magnet_link": "magnet:?xt=urn:btih:deadbeef",
                  "source_url": "https://1337x.example/torrent/12345",
                  "seeders": "120",
                  "leechers": "4",
                  "size": "700 MB",
                  "size_bytes": 734003200,
                  "uploader": "goodUploader"
                },
                {
                  "source": "prowlarr",
                  "name": "Minimal Result"
                }
              ]
            }
        """.trimIndent()

        val parsed = apiJson.decodeFromString<SourceSearchResponse>(json)
        assertEquals(2, parsed.items.size)

        val first = parsed.items[0]
        assertEquals("1337x", first.source)
        assertEquals("12345", first.torrentId)
        assertEquals("deadbeef", first.infoHash)
        assertEquals("magnet:?xt=urn:btih:deadbeef", first.magnetLink)
        assertEquals(734003200L, first.sizeBytes)
        assertEquals("120", first.seeders)

        val second = parsed.items[1]
        assertEquals("prowlarr", second.source)
        assertNull(second.magnetLink)
        assertNull(second.sizeBytes)
    }

    @Test
    fun `parses GitHub release list including unknown keys`() {
        val json = """
            [
              {
                "tag_name": "v1.2.0",
                "name": "Mekamb Music 1.2.0",
                "body": "- New features\n- Bug fixes",
                "draft": false,
                "prerelease": false,
                "published_at": "2026-07-01T00:00:00Z",
                "html_url": "https://github.com/LofisMusk/mekamb-music/releases/tag/v1.2.0",
                "assets": [
                  {
                    "name": "MekambMusic-1.2.0-macos-arm64.dmg",
                    "browser_download_url": "https://github.com/LofisMusk/mekamb-music/releases/download/v1.2.0/MekambMusic-1.2.0-macos-arm64.dmg",
                    "size": 104857600,
                    "content_type": "application/octet-stream"
                  },
                  {
                    "name": "SHA256SUMS.txt",
                    "browser_download_url": "https://github.com/LofisMusk/mekamb-music/releases/download/v1.2.0/SHA256SUMS.txt",
                    "size": 512
                  }
                ]
              },
              {
                "tag_name": "android-7",
                "draft": false,
                "prerelease": false,
                "assets": []
              },
              {
                "tag_name": "v1.3.0-beta.1",
                "draft": true,
                "prerelease": true
              }
            ]
        """.trimIndent()

        val parsed = apiJson.decodeFromString<List<GhRelease>>(json)
        assertEquals(3, parsed.size)

        val first = parsed[0]
        assertEquals("v1.2.0", first.tagName)
        assertEquals("Mekamb Music 1.2.0", first.name)
        assertEquals(false, first.draft)
        assertEquals(2, first.assets.size)
        assertEquals("MekambMusic-1.2.0-macos-arm64.dmg", first.assets[0].name)
        assertEquals(104857600L, first.assets[0].size)
        assertTrue(first.assets[0].browserDownloadUrl.startsWith("https://github.com/"))

        assertEquals("android-7", parsed[1].tagName)
        assertTrue(parsed[1].assets.isEmpty())

        assertEquals(true, parsed[2].draft)
        assertEquals(true, parsed[2].prerelease)
        assertTrue(parsed[2].assets.isEmpty())
    }
}
