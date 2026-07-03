import XCTest
@testable import MekambMusicNative

final class MekambMusicNativeTests: XCTestCase {

    // MARK: - Endpoint normalization

    func testNormalizedEndpointAddsHttpScheme() {
        let state = AppState()
        state.apiEndpoint = "192.168.1.50:8000"
        XCTAssertEqual(state.normalizedEndpoint, "http://192.168.1.50:8000")
    }

    func testNormalizedEndpointKeepsExistingScheme() {
        let state = AppState()
        state.apiEndpoint = "https://music.example.com"
        XCTAssertEqual(state.normalizedEndpoint, "https://music.example.com")
    }

    func testNormalizedEndpointTrimsTrailingSlashAndWhitespace() {
        let state = AppState()
        state.apiEndpoint = "  http://192.168.1.50:8000/  "
        XCTAssertEqual(state.normalizedEndpoint, "http://192.168.1.50:8000")
    }

    func testNormalizedEndpointEmptyStaysEmpty() {
        let state = AppState()
        state.apiEndpoint = ""
        XCTAssertEqual(state.normalizedEndpoint, "")
    }

    // MARK: - Endpoint warning

    func testEndpointWarningFlagsLocalhostOnDevice() {
        let state = AppState()
        state.apiEndpoint = "http://localhost:8000"
        XCTAssertNotNil(state.endpointWarning)
    }

    func testEndpointWarningFlagsEmptyEndpoint() {
        let state = AppState()
        state.apiEndpoint = ""
        XCTAssertNotNil(state.endpointWarning)
    }

    // MARK: - ApiTrack decoding

    func testApiTrackDecodesFromBackendJSON() throws {
        let json = """
        {
            "id": "abc123",
            "title": "Test Song",
            "artist": "Test Artist",
            "album": "Test Album",
            "original_filename": "test.mp3",
            "media_type": "audio/mpeg",
            "duration_seconds": 185.5,
            "size_bytes": 4200000,
            "created_at": "2026-01-01T00:00:00Z"
        }
        """.data(using: .utf8)!

        let track = try JSONDecoder().decode(ApiTrack.self, from: json)

        XCTAssertEqual(track.id, "abc123")
        XCTAssertEqual(track.title, "Test Song")
        XCTAssertEqual(track.artist, "Test Artist")
        XCTAssertEqual(track.durationSeconds, 185.5)
    }

    func testApiTrackDecodesWithNullOptionalFields() throws {
        let json = """
        {
            "id": "def456",
            "title": "Untitled",
            "artist": null,
            "album": null,
            "original_filename": null,
            "media_type": null,
            "duration_seconds": null,
            "size_bytes": null,
            "created_at": null
        }
        """.data(using: .utf8)!

        let track = try JSONDecoder().decode(ApiTrack.self, from: json)

        XCTAssertEqual(track.displayArtist, "Unknown Artist")
        XCTAssertEqual(track.displayAlbum, "Unknown Album")
        XCTAssertEqual(track.durationText, "0:00")
    }

    func testApiTrackDurationTextFormatsMinutesAndSeconds() throws {
        let json = """
        {"id": "x", "title": "t", "artist": null, "album": null,
         "original_filename": null, "media_type": null,
         "duration_seconds": 65, "size_bytes": null, "created_at": null}
        """.data(using: .utf8)!

        let track = try JSONDecoder().decode(ApiTrack.self, from: json)
        XCTAssertEqual(track.durationText, "1:05")
    }

    // MARK: - File size formatting

    func testFormatFileSizeBytes() {
        XCTAssertEqual(formatFileSize(0), "0 B")
        XCTAssertEqual(formatFileSize(500), "500 B")
    }

    func testFormatFileSizeMegabytes() {
        XCTAssertEqual(formatFileSize(5 * 1024 * 1024), "5.0 MB")
    }
}
