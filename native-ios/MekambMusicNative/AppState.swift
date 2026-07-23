import AVFoundation
import Foundation
import ImageIO
import MediaPlayer
import Network
import SwiftUI
import UIKit

struct ApiTrack: Identifiable, Codable, Hashable {
    let id: String
    let title: String
    let artist: String?
    let album: String?
    let originalFilename: String?
    let mediaType: String?
    let durationSeconds: Double?
    let sizeBytes: Int?
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case artist
        case album
        case originalFilename = "original_filename"
        case mediaType = "media_type"
        case durationSeconds = "duration_seconds"
        case sizeBytes = "size_bytes"
        case createdAt = "created_at"
    }

    var displayArtist: String { artist?.isEmpty == false ? artist! : "Unknown Artist" }
    var displayAlbum: String { album?.isEmpty == false ? album! : "Unknown Album" }
    var durationText: String {
        guard let durationSeconds, durationSeconds.isFinite, durationSeconds > 0 else { return "0:00" }
        let total = Int(durationSeconds.rounded())
        return "\(total / 60):\(String(format: "%02d", total % 60))"
    }
}

func formatFileSize(_ bytes: Int) -> String {
    guard bytes > 0 else { return "0 B" }
    let units = ["B", "KB", "MB", "GB", "TB"]
    var value = Double(bytes)
    var index = 0
    while value >= 1024, index < units.count - 1 {
        value /= 1024
        index += 1
    }
    return index == 0 ? "\(Int(value)) \(units[index])" : String(format: "%.1f %@", value, units[index])
}

struct Album: Identifiable, Hashable {
    let id: String
    let title: String
    let artist: String
    let tracks: [ApiTrack]
    let coverTrackId: String?

    var trackCountText: String { tracks.count == 1 ? "1 song" : "\(tracks.count) songs" }
}

struct DailyMix: Identifiable, Hashable {
    let id: String
    let title: String
    let description: String
    let seedLabel: String?
    let tracks: [ApiTrack]
}

struct TrackListResponse: Codable { let items: [ApiTrack] }
struct LikedTrackItem: Codable { let track: ApiTrack }
struct LikedTracksResponse: Codable { let items: [LikedTrackItem] }

struct PlaylistSummary: Identifiable, Codable, Hashable {
    let id: String
    let name: String
    let trackCount: Int
    let createdAt: String?
    let updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case trackCount = "track_count"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct PlaylistTrackItem: Codable, Hashable {
    let position: Int
    let addedAt: String?
    let track: ApiTrack

    enum CodingKeys: String, CodingKey {
        case position
        case addedAt = "added_at"
        case track
    }
}

struct PlaylistDetail: Identifiable, Codable, Hashable {
    let id: String
    let name: String
    let tracks: [PlaylistTrackItem]
    let createdAt: String?
    let updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case tracks
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    var trackCountText: String {
        tracks.count == 1 ? "1 song" : "\(tracks.count) songs"
    }

    var orderedTracks: [ApiTrack] {
        tracks.sorted { left, right in left.position < right.position }.map(\.track)
    }
}

struct PlaylistListResponse: Codable { let items: [PlaylistSummary] }

struct PlaylistNamePayload: Encodable {
    let name: String
}

struct PlaylistTrackPayload: Encodable {
    let trackId: String

    enum CodingKeys: String, CodingKey {
        case trackId = "track_id"
    }
}

struct RecommendationTrackPayload: Codable {
    let track: ApiTrack
    let score: Double?
    let reasons: [String]?
}

struct DailyMixPayload: Codable {
    let id: String
    let title: String
    let description: String
    let seedLabel: String?
    let tracks: [RecommendationTrackPayload]

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case description
        case seedLabel = "seed_label"
        case tracks
    }
}

struct PersonalizedHomeResponse: Codable {
    let recommendedTracks: [RecommendationTrackPayload]
    let dailyMixes: [DailyMixPayload]

    enum CodingKeys: String, CodingKey {
        case recommendedTracks = "recommended_tracks"
        case dailyMixes = "daily_mixes"
    }
}

struct RecentPlayPayload: Codable, Hashable {
    let track: ApiTrack
    let playedAt: String?
    let completed: Bool?
    let listenRatio: Double?

    enum CodingKeys: String, CodingKey {
        case track
        case playedAt = "played_at"
        case completed
        case listenRatio = "listen_ratio"
    }
}

struct RecentPlaysResponse: Codable { let items: [RecentPlayPayload] }

struct AutoplayQueuePayload: Codable {
    let seedTrack: ApiTrack
    let tracks: [RecommendationTrackPayload]

    enum CodingKeys: String, CodingKey {
        case seedTrack = "seed_track"
        case tracks
    }
}

struct PlaybackEventBody: Encodable {
    let completed: Bool
    let listenRatio: Double?
    let source: String

    enum CodingKeys: String, CodingKey {
        case completed
        case listenRatio = "listen_ratio"
        case source
    }
}

struct OfflineTrackRecord: Codable, Hashable {
    let track: ApiTrack
    let relativePath: String
    let downloadedAt: Date
    let sizeBytes: Int?
}

/// Last-known-good disk snapshot of the library, used to hydrate the UI instantly on cold start
/// before `refreshLibrary()`'s network calls resolve. See `loadCachedLibrarySnapshot()`.
struct LibrarySnapshot: Codable {
    let tracks: [ApiTrack]
    let likedTrackIds: Set<String>
    let playlists: [PlaylistDetail]
    // Optional so snapshots written before play-history caching still decode.
    let recentPlays: [RecentPlayPayload]?
}

enum TorrentSource: String, Codable, CaseIterable, Identifiable {
    case pirateBay = "piratebay"
    case thirteenThirtySevenX = "1337x"
    case indexer = "indexer"

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .pirateBay:
            return "Pirate Bay"
        case .thirteenThirtySevenX:
            return "1337x"
        case .indexer:
            return "Indexers"
        }
    }

    var searchPath: String {
        switch self {
        case .pirateBay:
            return "/sources/piratebay/search"
        case .thirteenThirtySevenX:
            return "/sources/1337x/search"
        case .indexer:
            return "/sources/indexers/search"
        }
    }

    var importPath: String {
        switch self {
        case .pirateBay:
            return "/imports/piratebay"
        case .thirteenThirtySevenX:
            return "/imports/1337x"
        case .indexer:
            return "/imports/indexer"
        }
    }
}

struct TorrentResult: Identifiable, Codable, Hashable {
    let name: String
    let torrentId: String
    let source: TorrentSource
    let infoHash: String?
    let magnetLink: String?
    let sourceUrl: String?
    let seeders: String?
    let leechers: String?
    let sizeBytes: Int?
    let sizeLabel: String?
    let uploader: String?

    enum CodingKeys: String, CodingKey {
        case name
        case torrentId = "torrent_id"
        case source
        case infoHash = "info_hash"
        case magnetLink = "magnet_link"
        case sourceUrl = "source_url"
        case seeders
        case leechers
        case sizeBytes = "size_bytes"
        case sizeLabel = "size"
        case uploader
    }

    init(
        name: String,
        torrentId: String,
        source: TorrentSource,
        infoHash: String?,
        magnetLink: String?,
        sourceUrl: String?,
        seeders: String?,
        leechers: String?,
        sizeBytes: Int?,
        sizeLabel: String?,
        uploader: String?
    ) {
        self.name = name
        self.torrentId = torrentId
        self.source = source
        self.infoHash = infoHash
        self.magnetLink = magnetLink
        self.sourceUrl = sourceUrl
        self.seeders = seeders
        self.leechers = leechers
        self.sizeBytes = sizeBytes
        self.sizeLabel = sizeLabel
        self.uploader = uploader
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        name = try container.decode(String.self, forKey: .name)
        torrentId = try container.decode(String.self, forKey: .torrentId)
        source = (try? container.decode(TorrentSource.self, forKey: .source)) ?? .pirateBay
        infoHash = try container.decodeIfPresent(String.self, forKey: .infoHash)
        magnetLink = try container.decodeIfPresent(String.self, forKey: .magnetLink)
        sourceUrl = try container.decodeIfPresent(String.self, forKey: .sourceUrl)
        seeders = try container.decodeIfPresent(String.self, forKey: .seeders)
        leechers = try container.decodeIfPresent(String.self, forKey: .leechers)
        sizeBytes = try container.decodeIfPresent(Int.self, forKey: .sizeBytes)
        sizeLabel = try container.decodeIfPresent(String.self, forKey: .sizeLabel)
        uploader = try container.decodeIfPresent(String.self, forKey: .uploader)
    }

    var id: String { "\(source.rawValue):\(torrentId)" }
    var sizeText: String {
        guard let sizeBytes, sizeBytes > 0 else {
            if let sizeLabel, !sizeLabel.isEmpty { return sizeLabel }
            return "0 B"
        }
        let units = ["B", "KB", "MB", "GB", "TB"]
        var value = Double(sizeBytes)
        var index = 0
        while value >= 1024, index < units.count - 1 {
            value /= 1024
            index += 1
        }
        return index == 0 ? "\(Int(value)) \(units[index])" : String(format: "%.1f %@", value, units[index])
    }

    func withSource(_ source: TorrentSource) -> TorrentResult {
        TorrentResult(
            name: name,
            torrentId: torrentId,
            source: source,
            infoHash: infoHash,
            magnetLink: magnetLink,
            sourceUrl: sourceUrl,
            seeders: seeders,
            leechers: leechers,
            sizeBytes: sizeBytes,
            sizeLabel: sizeLabel,
            uploader: uploader
        )
    }
}

struct TorrentSearchResponse: Codable { let items: [TorrentResult] }

struct IndexerImportPayload: Encodable {
    let name: String
    let torrentId: String?
    let infoHash: String
    let magnetLink: String
    let uploader: String?
    let sourceUrl: String?

    enum CodingKeys: String, CodingKey {
        case name
        case torrentId = "torrent_id"
        case infoHash = "info_hash"
        case magnetLink = "magnet_link"
        case uploader
        case sourceUrl = "source_url"
    }
}

enum SearchMode: String, CaseIterable, Identifiable {
    case library = "Library"
    case catalog = "Add Music"
    var id: String { rawValue }

    /// True when the mode queries the server (the Lidarr-backed catalog) rather
    /// than filtering the already-loaded library in memory.
    var searchesRemoteSources: Bool {
        self == .catalog
    }
}

// ── Catalog (self-service Lidarr acquisition) ────────────────────────────────
enum CatalogKind: String, Codable, CaseIterable, Identifiable {
    case artist
    case album
    var id: String { rawValue }
    var label: String { self == .artist ? "Artists" : "Albums" }
}

struct CatalogItem: Identifiable, Codable, Hashable {
    let kind: String
    let foreignId: String
    let title: String
    let artist: String?
    let artistForeignId: String?
    let disambiguation: String?
    let year: Int?

    enum CodingKeys: String, CodingKey {
        case kind
        case foreignId = "foreign_id"
        case title
        case artist
        case artistForeignId = "artist_foreign_id"
        case disambiguation
        case year
    }

    var id: String { "\(kind):\(foreignId)" }
    var subtitle: String {
        var parts: [String] = []
        if let artist, !artist.isEmpty { parts.append(artist) }
        if let year { parts.append(String(year)) }
        if let disambiguation, !disambiguation.isEmpty { parts.append(disambiguation) }
        return parts.joined(separator: " · ")
    }
}

struct CatalogSearchResponse: Codable {
    let items: [CatalogItem]
    let kind: String
    let query: String
}

struct CatalogAddRequestBody: Encodable {
    let kind: String
    let foreignId: String
    let title: String
    let artist: String?
    let artistForeignId: String?

    enum CodingKeys: String, CodingKey {
        case kind
        case foreignId = "foreign_id"
        case title
        case artist
        case artistForeignId = "artist_foreign_id"
    }
}

struct CatalogRequestItem: Identifiable, Codable, Hashable {
    let id: String
    let kind: String
    let foreignId: String
    let title: String
    let status: String

    enum CodingKeys: String, CodingKey {
        case id
        case kind
        case foreignId = "foreign_id"
        case title
        case status
    }
}

struct CatalogRequestListResponse: Codable { let items: [CatalogRequestItem] }

// ── Per-user libraries (curated subsets of the shared catalog) ───────────────
struct LibrarySummary: Identifiable, Codable, Hashable {
    let id: String
    let name: String
    let trackCount: Int

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case trackCount = "track_count"
    }
}

struct LibraryListResponse: Codable { let items: [LibrarySummary] }

struct LibraryTrackEntry: Codable, Hashable {
    let position: Int
    let track: ApiTrack
}

struct LibraryDetail: Identifiable, Codable, Hashable {
    let id: String
    let name: String
    let tracks: [LibraryTrackEntry]

    var orderedTracks: [ApiTrack] {
        tracks.sorted { $0.position < $1.position }.map(\.track)
    }
}

// ── Imports (real backend import-tracking API, GET /imports) ────────────────
struct ImportRecordResponse: Identifiable, Codable, Hashable {
    let id: String
    let source: String
    let torrentId: String
    let uploader: String
    let sourceUrl: String
    let status: String
    let errorMessage: String?
    let createdAt: String
    let updatedAt: String

    enum CodingKeys: String, CodingKey {
        case id, source, uploader, status
        case torrentId = "torrent_id"
        case sourceUrl = "source_url"
        case errorMessage = "error_message"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    var normalizedStatus: String { status.lowercased() }
    var isActive: Bool { ["queued", "downloading", "ready_to_import"].contains(normalizedStatus) }
    var isFailed: Bool { normalizedStatus == "failed" }
    var isImported: Bool { normalizedStatus == "imported" }
    var isCanceled: Bool { normalizedStatus == "canceled" }

    /// `ImportRecordResponse` carries no title — best-effort display name from whichever
    /// identifying field is present (the source URL's last path segment, the torrent id, or a
    /// truncated import id as a last resort).
    var displayName: String {
        if let last = sourceUrl.split(separator: "/").last, !last.isEmpty {
            return last.removingPercentEncoding ?? String(last)
        }
        if !torrentId.isEmpty { return torrentId }
        return "Import \(id.prefix(8))"
    }

    var statusLabel: String {
        switch normalizedStatus {
        case "queued": return "Queued"
        case "downloading": return "Downloading"
        case "ready_to_import": return "Ready"
        case "imported": return "Imported"
        case "failed": return "Failed"
        case "canceled": return "Canceled"
        default: return status.capitalized
        }
    }

    var stageDescription: String {
        switch normalizedStatus {
        case "queued": return "Waiting for worker"
        case "downloading": return "Downloading from source"
        case "ready_to_import": return "Validating & ingesting"
        default: return statusLabel
        }
    }
}

struct ImportListResponse: Codable { let items: [ImportRecordResponse] }

/// Minimal projection of `GET /library/summary` — only the fields the Imports tab badge needs.
struct LibrarySummaryResponse: Decodable {
    let activeImportCount: Int
    let failedImportCount: Int

    enum CodingKeys: String, CodingKey {
        case activeImportCount = "active_import_count"
        case failedImportCount = "failed_import_count"
    }
}

/// `GET /tracks/cache/stats` / `POST /tracks/cache/cleanup` response.
struct CacheStatsResponse: Codable {
    let totalTracks: Int
    let totalSizeMb: Double
    let staleTracks: Int
    let cacheTtlDays: Int
    let libraryRoot: String

    enum CodingKeys: String, CodingKey {
        case totalTracks = "total_tracks"
        case totalSizeMb = "total_size_mb"
        case staleTracks = "stale_tracks"
        case cacheTtlDays = "cache_ttl_days"
        case libraryRoot = "library_root"
    }
}

enum MusicTab: String, CaseIterable, Identifiable {
    case home = "Home"
    case library = "Library"
    case addMusic = "Add Music"
    case imports = "Imports"
    case search = "Search"
    case albums = "Albums"
    case playlists = "Playlists"
    case liked = "Liked"
    case artist = "Artist"
    case mix = "Mix"
    case settings = "Settings"
    var id: String { rawValue }

    /// Tabs shown in the bottom bar. The rest of the cases are non-bar "pushed detail" states —
    /// reached by tapping a shelf card / row / avatar — mirroring how `albums`/`playlists`
    /// already worked before this screen set grew: `selectedTab` doubles as the current screen,
    /// and detail screens return to `lastBarTab` instead of maintaining a real nav stack (this
    /// matches the reference design's own back-button behavior, which always returns to the
    /// originating tab rather than a nested history).
    static var barItems: [MusicTab] { [.home, .library, .addMusic, .imports] }
}

enum RepeatMode: String, CaseIterable, Identifiable {
    case off
    case all
    case one

    var id: String { rawValue }

    var iconName: String {
        switch self {
        case .off, .all:
            return "repeat"
        case .one:
            return "repeat.1"
        }
    }

    var label: String {
        switch self {
        case .off:
            return "Repeat Off"
        case .all:
            return "Repeat All"
        case .one:
            return "Repeat One"
        }
    }

    var isActive: Bool { self != .off }
}

/// User-selectable streaming quality. `auto` picks lossless on unmetered Wi-Fi and AAC on
/// constrained/cellular connections; `aac` always transcodes lossless sources to AAC; `lossless`
/// always streams the original file.
enum PlaybackQuality: String, CaseIterable, Identifiable {
    case auto
    case aac
    case lossless

    var id: String { rawValue }
    var label: String {
        switch self {
        case .auto: return "Auto"
        case .aac: return "AAC"
        case .lossless: return "Lossless"
        }
    }
    var detail: String {
        switch self {
        case .auto: return "Lossless on Wi‑Fi, AAC on cellular"
        case .aac: return "Smaller files, saves data"
        case .lossless: return "Original quality (FLAC)"
        }
    }
}

@MainActor
final class AppState: ObservableObject {
    @AppStorage("mekambMusicApiEndpoint") var apiEndpoint: String = ""
    // The bearer credential sent on every request: the account session token from
    // /auth/login. There is no raw API-token scheme anymore — you must log in.
    @AppStorage("mekambMusicApiToken") var apiToken: String = ""
    @AppStorage("mekambMusicAccountUsername") var accountUsername: String = ""
    @AppStorage("mekambMusicAccountEmail") var accountEmail: String = ""
    // Whether the signed-in account is an admin — gates the in-app approval panel.
    @AppStorage("mekambMusicAccountIsAdmin") var accountIsAdmin: Bool = false
    @AppStorage("mekambMusicAutoplaySimilarEnabled") var autoplaySimilarEnabled: Bool = true
    @AppStorage("mekambMusicPlaybackQuality") var playbackQuality: PlaybackQuality = .auto
    /// "Prefetch queued tracks" toggle in Settings — gates the upcoming-queue background cache.
    @AppStorage("mekambMusicPrefetchQueuedTracks") var prefetchQueuedTracksEnabled: Bool = true
    /// "Download over cellular" toggle in Settings — gates offline downloads while on a
    /// constrained/cellular connection (see `isConstrainedNetwork`).
    @AppStorage("mekambMusicDownloadOverCellular") var downloadOverCellularEnabled: Bool = false
    @AppStorage("mekambMusicLastTrackId") private var savedPlaybackTrackId: String = ""
    @AppStorage("mekambMusicLastElapsedTime") private var savedPlaybackElapsedTime: Double = 0

    @Published var searchMode: SearchMode = .library
    @Published var selectedTab: MusicTab = .home {
        didSet {
            if MusicTab.barItems.contains(selectedTab) { lastBarTab = selectedTab }
        }
    }
    /// The last real bottom-bar tab the user was on — every pushed detail screen's back button
    /// returns here, mirroring the reference design (which always backs out to the originating
    /// tab rather than keeping a nested history).
    @Published private(set) var lastBarTab: MusicTab = .home
    @Published var searchText: String = ""
    /// Search text for the Add Music (catalog) tab — kept separate from `searchText` so the
    /// library-search screen and the catalog-search tab never bleed into each other.
    @Published var catalogQuery: String = ""
    @Published var selectedArtistName: String?
    @Published var selectedMixId: String?

    /// Clears any in-progress query/results — used when leaving the Search tab.
    func resetSearch() {
        searchText = ""
        searchMode = .library
        catalogItems = []
    }
    @Published var tracks: [ApiTrack] = []
    @Published var likedTrackIds: Set<String> = []
    @Published var catalogItems: [CatalogItem] = []
    @Published var catalogKind: CatalogKind = .artist
    @Published var catalogRequests: [CatalogRequestItem] = []
    @Published var addedCatalogIds: Set<String> = []
    @Published var libraries: [LibrarySummary] = []
    @Published var albumCovers: [String: UIImage] = [:]
    @Published var selectedAlbumId: String?
    @Published var selectedPlaylistId: String?
    @Published var isLoading = false
    @Published var isSearchingCatalog = false
    @Published var isTestingConnection = false
    @Published var isAuthenticating = false
    /// Outcome of the last login/migrate/register/logout attempt, shown in Settings.
    @Published var authStatusMessage: String?
    @Published var authStatusIsError = false
    @Published var connectionStatus: String?
    @Published var errorMessage: String?
    @Published var currentTrack: ApiTrack?
    @Published var isPlaying = false
    @Published var playbackProgress: Double = 0
    @Published var playbackQueue: [ApiTrack] = []
    @Published var shuffleEnabled = false
    @Published var repeatMode: RepeatMode = .off
    @Published var downloadingTrackIds: Set<String> = []
    @Published var downloadingAlbumIds: Set<String> = []
    @Published var offlineTrackIds: Set<String> = []
    @Published var offlineStorageBytes: Int = 0
    @Published var offlineStatusMessage: String?
    @Published private(set) var albums: [Album] = []
    @Published private(set) var playlists: [PlaylistDetail] = []
    @Published private(set) var homeRecommendedTracks: [ApiTrack] = []
    @Published private(set) var dailyMixes: [DailyMix] = []
    @Published private(set) var recentlyAddedTracks: [ApiTrack] = []
    @Published private(set) var recentlyAddedAlbums: [Album] = []
    @Published private(set) var downloadedTracks: [ApiTrack] = []
    @Published private(set) var likedTracksPreview: [ApiTrack] = []
    @Published private(set) var recentlyPlayedTracks: [ApiTrack] = []
    @Published private(set) var jumpBackInAlbums: [Album] = []
    @Published private(set) var albumsFeaturingLikedTracks: [Album] = []

    @Published var importRecords: [ImportRecordResponse] = []
    @Published var isLoadingImports = false
    @Published private(set) var activeImportCount: Int = 0

    @Published var cacheStats: CacheStatsResponse?
    @Published var isLoadingCacheStats = false
    @Published var isClearingCache = false

    private var player: AVPlayer?
    private var timeObserver: Any?
    private weak var timeObserverPlayer: AVPlayer?
    /// KVO on the live player's `timeControlStatus` so `isPlaying` tracks the *actual* transport
    /// state — including pauses/plays driven by the lock screen, Control Center, Siri, or audio
    /// interruptions, which never route through our own `togglePlayback()`.
    private var timeControlObserver: NSKeyValueObservation?
    private var playerItemEndObserver: NSObjectProtocol?
    private var playerItemStalledObserver: NSObjectProtocol?
    private var playerItemFailedObserver: NSObjectProtocol?
    private var isLoadingAlbumCovers = false
    private var failedAlbumCoverIds: Set<String> = []
    private var didRestorePlaybackState = false
    private var offlineRecords: [String: OfflineTrackRecord] = [:]
    private var backendRecommendedTrackIds: [String] = []
    private var backendDailyMixes: [DailyMix] = []
    private var lastPersonalizationRefreshAt: Date?
    private var playbackPrefetchTask: Task<Void, Never>?
    private var playbackPrefetchingTrackIds: Set<String> = []
    private var currentTrackCacheTask: Task<Void, Never>?
    private var pathMonitor: NWPathMonitor?
    private var isAwaitingReconnectToResume = false
    private var isRecoveringPlayback = false
    /// Raw play-history feed from GET /tracks/recent (newest first); shelves derive from it.
    private var recentPlayEvents: [RecentPlayPayload] = []
    /// Backend radio continuation prefetched while the last queued track plays, consumed
    /// synchronously in nextTrack() so autoplay is gapless. Seed id guards against staleness.
    private var autoplayStash: [ApiTrack] = []
    private var autoplayStashSeedId: String?
    private var autoplayPrefetchTask: Task<Void, Never>?
    /// Outgoing-track listening session used to report real skip/completion signals.
    private var playSession: (track: ApiTrack, maxElapsed: TimeInterval)?

    /// Live connectivity state, used to auto-resume playback once the network returns after a
    /// drop that happened before the current track finished caching locally.
    @Published private(set) var isNetworkReachable = true
    /// True on cellular/metered/constrained links; drives "Auto" quality to pick AAC.
    @Published private(set) var isConstrainedNetwork = false
    /// Short codec label ("FLAC"/"AAC"/…) of the track currently playing, shown next to it.
    @Published private(set) var currentCodecBadge: String?

    private struct PlaybackSource {
        let url: URL
        let headers: [String: String]?
    }

    init() {
        configureAudioSession()
        configureRemoteCommandCenter()
        startNetworkMonitoring()
        // Deferred to a Task so `init()` returns immediately and the scene can render its first
        // frame. These do disk I/O (JSON decode, per-file existence checks) and rebuild derived
        // state (albums/recommendations/mixes) — running them inline here used to block the whole
        // app launch until they finished, which on a real library is slow enough that iOS treats
        // it as a launch hang and kills the process before anything is ever drawn.
        Task { @MainActor [weak self] in
            self?.loadCachedLibrarySnapshot()
            self?.loadOfflineLibrary()
            // Paint disk-cached album covers immediately after the snapshot hydrates, instead of
            // waiting for refreshLibrary()'s full network round-trip to finish first — otherwise
            // the home sits on gradient placeholders for the whole "connecting" window even though
            // the real covers are already on disk from a previous run.
            await self?.loadMissingAlbumCovers()
        }
    }

    deinit {
        if let timeObserver, let timeObserverPlayer {
            timeObserverPlayer.removeTimeObserver(timeObserver)
        }
        if let playerItemEndObserver {
            NotificationCenter.default.removeObserver(playerItemEndObserver)
        }
        if let playerItemStalledObserver {
            NotificationCenter.default.removeObserver(playerItemStalledObserver)
        }
        if let playerItemFailedObserver {
            NotificationCenter.default.removeObserver(playerItemFailedObserver)
        }
        timeControlObserver?.invalidate()
        pathMonitor?.cancel()
        currentTrackCacheTask?.cancel()
        autoplayPrefetchTask?.cancel()
        player?.pause()
    }

    var normalizedEndpoint: String { normalizeEndpoint(apiEndpoint) }

    var endpointWarning: String? {
        let normalized = normalizedEndpoint.lowercased()
        if normalized.isEmpty { return "Set your backend URL, for example http://192.168.1.50:8000." }
        if normalized.contains("localhost") || normalized.contains("127.0.0.1") {
            return "On a real iPhone, localhost points to the iPhone. Use your Mac/server LAN IP instead."
        }
        return nil
    }

    var canUseApi: Bool {
        !normalizedEndpoint.isEmpty && !apiToken.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var offlineTrackCount: Int { offlineTrackIds.count }

    var offlineStorageText: String { formatFileSize(offlineStorageBytes) }

    private func rebuildDerivedLibraryState() {
        let rebuiltAlbums = buildAlbumGroups(from: tracks)
        let tracksById = Dictionary(uniqueKeysWithValues: tracks.map { ($0.id, $0) })
        let localRecommendations = buildHomeRecommendedTracks()
        let backendRecommendations = backendRecommendedTrackIds.compactMap { tracksById[$0] }
        let remappedBackendMixes = backendDailyMixes.compactMap { mix -> DailyMix? in
            let remappedTracks = mix.tracks.compactMap { tracksById[$0.id] }
            guard !remappedTracks.isEmpty else { return nil }
            return DailyMix(
                id: mix.id,
                title: mix.title,
                description: mix.description,
                seedLabel: mix.seedLabel,
                tracks: remappedTracks
            )
        }
        albums = rebuiltAlbums
        homeRecommendedTracks = backendRecommendations.isEmpty ? localRecommendations : Array(backendRecommendations.prefix(18))
        dailyMixes = remappedBackendMixes.isEmpty
            ? buildLocalDailyMixes(recommendedTracks: homeRecommendedTracks)
            : remappedBackendMixes
        recentlyAddedTracks = Array(tracks.sorted { left, right in
            let leftCreated = createdTimestamp(left)
            let rightCreated = createdTimestamp(right)
            if leftCreated != rightCreated { return leftCreated > rightCreated }
            return stableLibraryTrackOrder(left, right)
        }.prefix(18))
        recentlyAddedAlbums = Array(rebuiltAlbums.sorted { left, right in
            let leftCreated = left.tracks.map(createdTimestamp).max() ?? 0
            let rightCreated = right.tracks.map(createdTimestamp).max() ?? 0
            if leftCreated != rightCreated { return leftCreated > rightCreated }
            return stableAlbumOrder(left, right)
        }.prefix(12))
        downloadedTracks = Array(tracks.filter { offlineTrackIds.contains($0.id) }.sorted(by: stableLibraryTrackOrder).prefix(18))
        likedTracksPreview = Array(tracks.filter { likedTrackIds.contains($0.id) }.sorted(by: stableLibraryTrackOrder).prefix(18))
        rebuildPlayHistoryShelves(rebuiltAlbums: rebuiltAlbums, tracksById: tracksById)
    }

    /// Derives the play-history-driven home shelves from `recentPlayEvents`:
    /// recently played (newest first, distinct), "Jump back in" (albums you listened to
    /// 1–21 days ago but not today), and "Albums featuring songs you like".
    private func rebuildPlayHistoryShelves(rebuiltAlbums: [Album], tracksById: [String: ApiTrack]) {
        var seenTrackIds = Set<String>()
        var playedTracks: [ApiTrack] = []
        for event in recentPlayEvents {
            guard seenTrackIds.insert(event.track.id).inserted else { continue }
            playedTracks.append(tracksById[event.track.id] ?? event.track)
        }
        recentlyPlayedTracks = Array(playedTracks.prefix(30))

        var albumByTrackId: [String: Album] = [:]
        for album in rebuiltAlbums {
            for track in album.tracks {
                albumByTrackId[track.id] = album
            }
        }

        let now = Date()
        let freshTrackIds = Set(recentlyPlayedTracks.prefix(8).map(\.id))
        var seenAlbumIds = Set<String>()
        var olderAlbums: [Album] = []
        for event in recentPlayEvents {
            guard let playedAt = event.playedAt.flatMap(parseISOTimestamp) else { continue }
            let age = now.timeIntervalSince(playedAt)
            guard age >= 86_400, age <= 21 * 86_400 else { continue }
            guard !freshTrackIds.contains(event.track.id) else { continue }
            guard let album = albumByTrackId[event.track.id] else { continue }
            guard seenAlbumIds.insert(album.id).inserted else { continue }
            olderAlbums.append(album)
        }
        jumpBackInAlbums = Array(olderAlbums.prefix(12))

        albumsFeaturingLikedTracks = Array(
            rebuiltAlbums
                .map { album in (album: album, likedCount: album.tracks.filter { likedTrackIds.contains($0.id) }.count) }
                .filter { $0.likedCount > 0 }
                .sorted { left, right in
                    if left.likedCount != right.likedCount { return left.likedCount > right.likedCount }
                    return stableAlbumOrder(left.album, right.album)
                }
                .map(\.album)
                .prefix(12)
        )
    }

    private func parseISOTimestamp(_ value: String) -> Date? {
        parseTimestampString(value).map { Date(timeIntervalSince1970: $0) }
    }

    private func buildAlbumGroups(from tracks: [ApiTrack]) -> [Album] {
        var groups: [(key: String, tracks: [ApiTrack])] = []
        for track in tracks {
            let key = albumGroupingKey(for: track)
            if let index = groups.firstIndex(where: { albumKeysMatch($0.key, key) }) {
                groups[index].tracks.append(track)
            } else {
                groups.append((key: key, tracks: [track]))
            }
        }

        return groups
            .map { key, albumTracks in
                let sortedTracks = albumTracks.sorted(by: originalAlbumTrackOrder)
                return Album(
                    id: key,
                    title: bestAlbumTitle(from: sortedTracks),
                    artist: bestAlbumArtist(from: sortedTracks),
                    tracks: sortedTracks,
                    coverTrackId: sortedTracks.first?.id
                )
            }
            .sorted(by: stableAlbumOrder)
    }

    private func buildHomeRecommendedTracks() -> [ApiTrack] {
        let seeds = tracks.filter { likedTrackIds.contains($0.id) || offlineTrackIds.contains($0.id) }
        if seeds.isEmpty {
            return Array(tracks.sorted(by: dailyStableTrackOrder(salt: "home-empty")).prefix(18))
        }

        let base = Array(seeds.sorted(by: dailyStableTrackOrder(salt: "home-seeds")).prefix(24))
        let baseIds = Set(base.map(\.id))
        let candidates = tracks.filter { !baseIds.contains($0.id) }
        let scored = candidates.map { candidate in
            let seedScore = base.map { similarityScore(candidate, to: $0) }.max() ?? 0
            let likedBoost = likedTrackIds.contains(candidate.id) ? 3 : 0
            let offlineBoost = offlineTrackIds.contains(candidate.id) ? 1 : 0
            let randomBoost = Int(stableShuffleScore(for: candidate.id, salt: dailyRecommendationSalt + "|home") % 6)
            return (track: candidate, score: seedScore + likedBoost + offlineBoost + randomBoost)
        }
        return Array(scored
            .sorted { left, right in
                if left.score != right.score { return left.score > right.score }
                return dailyStableTrackOrder(salt: "home-tie")(left.track, right.track)
            }
            .map(\.track)
            .prefix(18))
    }

    private func buildLocalDailyMixes(recommendedTracks: [ApiTrack]) -> [DailyMix] {
        guard !tracks.isEmpty else { return [] }
        let interestTracks = tracks.filter { likedTrackIds.contains($0.id) || offlineTrackIds.contains($0.id) }
        let seedTracks = interestTracks.isEmpty ? tracks : interestTracks
        let grouped = Dictionary(grouping: seedTracks) { normalizedGroupingValue($0.artist) ?? $0.displayArtist.lowercased() }
        let artistSeeds = grouped
            .map { key, group in (key: key, tracks: group, score: group.count + group.filter { likedTrackIds.contains($0.id) }.count * 2) }
            .sorted { left, right in
                if left.score != right.score { return left.score > right.score }
                return left.key < right.key
            }

        var mixes: [DailyMix] = []
        var usedTrackIds = Set<String>()
        for (index, seed) in artistSeeds.prefix(4).enumerated() {
            let label = seed.tracks.first?.displayArtist ?? "Your Library"
            let candidates = tracks
                .map { track in
                    (
                        track: track,
                        score: localDailyMixScore(track, seedTracks: seed.tracks, salt: "mix-\(index + 1)")
                    )
                }
                .sorted { left, right in
                    if left.score != right.score { return left.score > right.score }
                    return dailyStableTrackOrder(salt: "mix-\(index + 1)-tie")(left.track, right.track)
                }
                .map(\.track)

            var mixTracks: [ApiTrack] = []
            for track in candidates {
                if usedTrackIds.contains(track.id), tracks.count > 12 { continue }
                mixTracks.append(track)
                usedTrackIds.insert(track.id)
                if mixTracks.count >= 12 { break }
            }

            if !mixTracks.isEmpty {
                mixes.append(
                    DailyMix(
                        id: "local-daily-mix-\(dailyRecommendationSalt)-\(index + 1)",
                        title: "Daily Mix \(index + 1)",
                        description: "\(label) and similar picks",
                        seedLabel: label,
                        tracks: mixTracks
                    )
                )
            }
        }

        if mixes.isEmpty, !recommendedTracks.isEmpty {
            mixes.append(
                DailyMix(
                    id: "local-daily-mix-\(dailyRecommendationSalt)-1",
                    title: "Daily Mix 1",
                    description: "Fresh picks from your library",
                    seedLabel: nil,
                    tracks: Array(recommendedTracks.prefix(12))
                )
            )
        }
        return mixes
    }

    var filteredTracks: [ApiTrack] {
        let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let base = selectedTab == .liked ? tracks.filter { likedTrackIds.contains($0.id) } : tracks
        guard !query.isEmpty, searchMode == .library else { return base }
        return base.filter {
            $0.title.lowercased().contains(query)
            || $0.displayArtist.lowercased().contains(query)
            || $0.displayAlbum.lowercased().contains(query)
        }
    }

    var filteredAlbums: [Album] {
        let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !query.isEmpty, searchMode == .library else { return albums }
        return albums.filter {
            $0.title.lowercased().contains(query)
            || $0.artist.lowercased().contains(query)
        }
    }

    var selectedAlbum: Album? {
        guard let selectedAlbumId else { return nil }
        return albums.first { $0.id == selectedAlbumId }
    }

    var filteredPlaylists: [PlaylistDetail] {
        let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !query.isEmpty, searchMode == .library else { return playlists }
        return playlists.filter {
            $0.name.lowercased().contains(query)
            || $0.orderedTracks.contains { track in
                track.title.lowercased().contains(query)
                || track.displayArtist.lowercased().contains(query)
                || track.displayAlbum.lowercased().contains(query)
            }
        }
    }

    var selectedPlaylist: PlaylistDetail? {
        guard let selectedPlaylistId else { return nil }
        return playlists.first { $0.id == selectedPlaylistId }
    }

    var selectedMix: DailyMix? {
        guard let selectedMixId else { return nil }
        return dailyMixes.first { $0.id == selectedMixId }
    }

    /// Two-letter initials for the profile avatar, derived from the signed-in username.
    var accountInitials: String {
        let trimmed = accountUsername.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return "?" }
        let parts = trimmed.split(separator: " ")
        if parts.count >= 2, let first = parts[0].first, let second = parts[1].first {
            return String([first, second]).uppercased()
        }
        return String(trimmed.prefix(2)).uppercased()
    }

    var queueTracks: [ApiTrack] {
        playbackQueue.isEmpty ? playbackContextTracks() : playbackQueue
    }

    var upcomingQueueTracks: [ApiTrack] {
        guard let currentTrack else { return queueTracks }
        guard let index = queueTracks.firstIndex(where: { $0.id == currentTrack.id }) else { return queueTracks }
        let nextIndex = queueTracks.index(after: index)
        guard nextIndex < queueTracks.endIndex else { return [] }
        return Array(queueTracks[nextIndex...])
    }

    func coverImage(for track: ApiTrack) -> UIImage? {
        albumCovers[stableAlbumKey(for: track)]
    }

    func testConnection() async {
        guard !isTestingConnection else { return }
        isTestingConnection = true
        defer { isTestingConnection = false }
        errorMessage = nil
        connectionStatus = nil
        do {
            let _: EmptyResponse = try await request("/health", requiresAuth: false)
            connectionStatus = "Connected to \(normalizedEndpoint)"
        } catch {
            guard !isCancellation(error) else { return }
            let message = clean(error)
            connectionStatus = "Connection failed: \(message)"
            errorMessage = message
        }
    }

    // MARK: - Account auth (login, token migration, registration)

    var isSignedIn: Bool { !accountUsername.isEmpty }

    private var deviceName: String { "iOS (\(UIDevice.current.name))" }

    /// Stores a fresh account session: it replaces whatever session token was stored.
    private func applyAuthSession(token: String, user: AuthUserPayload) {
        apiToken = token
        accountUsername = user.username
        accountEmail = user.email
        accountIsAdmin = user.isAdmin
    }

    func login(identifier: String, password: String) async {
        await runAuthAction {
            let body = try JSONEncoder().encode(
                LoginPayload(identifier: identifier, password: password, deviceName: self.deviceName)
            )
            let session: AuthSessionPayload = try await self.request(
                "/auth/login", method: "POST", body: body, requiresAuth: false
            )
            self.applyAuthSession(token: session.token, user: session.user)
            return "Signed in as \(session.user.username)."
        }
    }

    func registerAccount(email: String, username: String, password: String) async {
        await runAuthAction {
            let body = try JSONEncoder().encode(
                RegisterPayload(email: email, username: username, password: password)
            )
            let response: AuthRegisterPayload = try await self.request(
                "/auth/register", method: "POST", body: body, requiresAuth: false
            )
            // A session comes back only when the account is approved on the spot
            // (bootstrap admins); everyone else waits for admin approval.
            if let sessionToken = response.token {
                self.applyAuthSession(token: sessionToken, user: response.user)
            }
            return response.message
        }
    }

    func logout() async {
        isAuthenticating = true
        defer { isAuthenticating = false }
        // Best effort: revoke the session server-side, but always clear locally.
        let _: EmptyResponse? = try? await request("/auth/logout", method: "POST")
        apiToken = ""
        accountUsername = ""
        accountEmail = ""
        accountIsAdmin = false
        authStatusMessage = "Logged out."
        authStatusIsError = false
        await refreshLibrary()
    }

    /// Refreshes the signed-in account from `/auth/me`. Keeps `accountIsAdmin`/status
    /// current (e.g. an admin grant landed after login) and, on a 401, signs out so
    /// a revoked/expired session drops back to the login gate instead of a dead UI.
    func loadCurrentAccount() async {
        guard isSignedIn else { return }
        do {
            let user: AuthUserPayload = try await request("/auth/me")
            accountUsername = user.username
            accountEmail = user.email
            accountIsAdmin = user.isAdmin
        } catch BackendError.api(let status, _) where status == 401 {
            await logout()
        } catch {
            // Network hiccup — keep the cached identity and try again next launch.
        }
    }

    // MARK: - Admin account approval

    func fetchAdminUsers(status: String? = nil) async -> [AuthUserPayload] {
        guard accountIsAdmin else { return [] }
        let path = status.map { "/admin/users?status=\($0)" } ?? "/admin/users"
        do {
            let response: AdminUserListPayload = try await request(path)
            return response.users
        } catch {
            authStatusMessage = clean(error)
            authStatusIsError = true
            return []
        }
    }

    /// Approve or reject a pending account. Returns true on success.
    @discardableResult
    func setUserApproval(id: String, approve: Bool) async -> Bool {
        let action = approve ? "approve" : "reject"
        do {
            let _: AuthUserPayload = try await request(
                "/admin/users/\(id)/\(action)", method: "POST"
            )
            return true
        } catch {
            authStatusMessage = clean(error)
            authStatusIsError = true
            return false
        }
    }

    private func runAuthAction(_ action: () async throws -> String) async {
        guard !isAuthenticating else { return }
        isAuthenticating = true
        defer { isAuthenticating = false }
        authStatusMessage = nil
        authStatusIsError = false
        do {
            authStatusMessage = try await action()
            await refreshLibrary()
        } catch {
            guard !isCancellation(error) else { return }
            authStatusMessage = clean(error)
            authStatusIsError = true
        }
    }

    func refreshLibrary() async {
        guard !isLoading else { return }
        guard canUseApi else {
            if offlineTrackIds.isEmpty {
                errorMessage = endpointWarning ?? "Set the API endpoint and log in in Settings."
            } else {
                errorMessage = nil
                offlineStatusMessage = "Offline library ready: \(offlineTrackCount) downloaded songs."
            }
            return
        }
        isLoading = true
        defer { isLoading = false }
        errorMessage = nil
        do {
            async let likedIds = loadAllLikedTrackIds()
            async let allTracks = loadAllTracks()
            async let playlistDetails = loadAllPlaylists()
            async let recentPlays = loadRecentPlays()
            let (newLikedIds, newTracks, newPlaylists, newRecentPlays) = try await (likedIds, allTracks, playlistDetails, recentPlays)
            likedTrackIds = newLikedIds
            if let newRecentPlays {
                recentPlayEvents = newRecentPlays
            }
            tracks = mergeTracks(
                existing: tracks,
                incoming: newTracks + newPlaylists.flatMap(\.orderedTracks) + (newRecentPlays ?? []).map(\.track)
            ).sorted(by: stableLibraryTrackOrder)
            playlists = remapPlaylists(newPlaylists)
            rebuildDerivedLibraryState()
            syncQueueWithLibrary()
            restorePlaybackStateIfNeeded()
            selectedAlbumId = selectedAlbumId.flatMap { id in albums.contains(where: { $0.id == id }) ? id : nil }
            selectedPlaylistId = selectedPlaylistId.flatMap { id in playlists.contains(where: { $0.id == id }) ? id : nil }
            selectedMixId = selectedMixId.flatMap { id in dailyMixes.contains(where: { $0.id == id }) ? id : nil }
            persistLibrarySnapshot()
            await loadPersonalizedHome()
            Task { await loadMissingAlbumCovers() }
            Task { await refreshImportBadge() }
        } catch {
            if !isCancellation(error) {
                let message = clean(error)
                errorMessage = offlineTrackIds.isEmpty ? message : "\(message) Showing downloaded songs."
            }
        }
    }

    func loadMissingAlbumCovers() async {
        guard !isLoadingAlbumCovers else { return }
        isLoadingAlbumCovers = true
        defer { isLoadingAlbumCovers = false }

        let targets = albums.compactMap { album -> (albumId: String, trackId: String)? in
            guard albumCovers[album.id] == nil, !failedAlbumCoverIds.contains(album.id), let trackId = album.coverTrackId else { return nil }
            return (album.id, trackId)
        }
        guard !targets.isEmpty else { return }

        // Disk-cached artwork is a fast local decode — apply every hit before spending any
        // network requests on the remaining misses.
        var networkTargets: [(albumId: String, trackId: String)] = []
        for target in targets {
            if let cached = loadCachedArtworkFromDisk(albumId: target.albumId) {
                albumCovers[target.albumId] = cached
            } else {
                networkTargets.append(target)
            }
        }
        guard !networkTargets.isEmpty else { return }

        // Fetch the actual network misses concurrently (bounded) instead of one at a time —
        // this was the dominant cost for libraries with many albums.
        let maxConcurrent = 6
        await withTaskGroup(of: (albumId: String, fetched: (image: UIImage, jpegData: Data)?).self) { group in
            var nextIndex = 0
            func addNext() {
                guard nextIndex < networkTargets.count else { return }
                let target = networkTargets[nextIndex]
                nextIndex += 1
                group.addTask {
                    let fetched = try? await self.loadArtwork(trackId: target.trackId)
                    return (target.albumId, fetched ?? nil)
                }
            }
            for _ in 0..<min(maxConcurrent, networkTargets.count) { addNext() }
            while let result = await group.next() {
                if let fetched = result.fetched {
                    albumCovers[result.albumId] = fetched.image
                    persistArtworkToDisk(fetched.jpegData, albumId: result.albumId)
                } else {
                    failedAlbumCoverIds.insert(result.albumId)
                }
                addNext()
            }
        }
    }

    // ── Catalog: request that Lidarr acquire an artist/album ─────────────────
    func searchCatalog() async {
        let query = catalogQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        guard canUseApi, !query.isEmpty else {
            catalogItems = []
            return
        }
        isSearchingCatalog = true
        errorMessage = nil
        do {
            let encoded = query.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? query
            let response: CatalogSearchResponse = try await request(
                "/catalog/search?kind=\(catalogKind.rawValue)&q=\(encoded)"
            )
            catalogItems = response.items
        } catch {
            if !isCancellation(error) {
                errorMessage = clean(error)
                catalogItems = []
            }
        }
        isSearchingCatalog = false
    }

    func addToCatalog(_ item: CatalogItem) async {
        errorMessage = nil
        do {
            let body = CatalogAddRequestBody(
                kind: item.kind,
                foreignId: item.foreignId,
                title: item.title,
                artist: item.artist,
                artistForeignId: item.artistForeignId
            )
            let response: CatalogRequestListResponse = try await request(
                "/catalog/add", method: "POST", body: try JSONEncoder().encode(body)
            )
            catalogRequests = response.items
            addedCatalogIds.insert(item.id)
        } catch {
            if !isCancellation(error) { errorMessage = clean(error) }
        }
    }

    func loadCatalogRequests() async {
        guard canUseApi else { return }
        do {
            let response: CatalogRequestListResponse = try await request("/catalog/requests")
            catalogRequests = response.items
        } catch {
            if !isCancellation(error) { errorMessage = clean(error) }
        }
    }

    /// Tracks by a specific artist, straight from the backend (there's no `/artists/{name}`
    /// detail endpoint, so the Artist screen's "Popular" section is sourced this way instead of
    /// relying on whatever happens to already be loaded into `tracks`).
    func fetchArtistTracks(_ artistName: String) async -> [ApiTrack] {
        guard canUseApi else { return tracks.filter { $0.displayArtist == artistName } }
        do {
            let encoded = artistName.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? artistName
            let response: TrackListResponse = try await request("/tracks?artist=\(encoded)&limit=200")
            return response.items
        } catch {
            if !isCancellation(error) { errorMessage = clean(error) }
            return tracks.filter { $0.displayArtist == artistName }
        }
    }

    // ── Imports (Imports tab) ─────────────────────────────────────────────────
    func loadImports(status: String? = nil) async {
        guard canUseApi else { return }
        isLoadingImports = true
        defer { isLoadingImports = false }
        do {
            var path = "/imports?limit=100"
            if let status { path += "&status=\(status)" }
            let response: ImportListResponse = try await request(path)
            importRecords = response.items.sorted { $0.createdAt > $1.createdAt }
            activeImportCount = importRecords.filter(\.isActive).count
        } catch {
            if !isCancellation(error) { errorMessage = clean(error) }
        }
    }

    /// Cheap badge-only refresh used before the user ever opens the Imports tab (e.g. right
    /// after launch/refresh). Once `loadImports()` has actually populated `importRecords`, that
    /// list is the more accurate source and this no longer overrides the count.
    func refreshImportBadge() async {
        guard canUseApi, importRecords.isEmpty else { return }
        do {
            let summary: LibrarySummaryResponse = try await request("/library/summary")
            activeImportCount = summary.activeImportCount
        } catch {
            // Silent — the badge just won't update this cycle.
        }
    }

    func cancelImport(_ record: ImportRecordResponse, deleteFiles: Bool = true) async {
        guard canUseApi else { return }
        do {
            let encoded = encodePathComponent(record.id)
            let updated: ImportRecordResponse = try await request(
                "/imports/\(encoded)/cancel?delete_files=\(deleteFiles)", method: "POST"
            )
            upsertImportRecord(updated)
        } catch {
            if !isCancellation(error) { errorMessage = clean(error) }
        }
    }

    func retryImport(_ record: ImportRecordResponse, deleteFiles: Bool = true) async {
        guard canUseApi else { return }
        do {
            let encoded = encodePathComponent(record.id)
            let updated: ImportRecordResponse = try await request(
                "/imports/\(encoded)/retry?delete_files=\(deleteFiles)", method: "POST"
            )
            upsertImportRecord(updated)
        } catch {
            if !isCancellation(error) { errorMessage = clean(error) }
        }
    }

    private func upsertImportRecord(_ record: ImportRecordResponse) {
        if let index = importRecords.firstIndex(where: { $0.id == record.id }) {
            importRecords[index] = record
        } else {
            importRecords.insert(record, at: 0)
        }
        activeImportCount = importRecords.filter(\.isActive).count
    }

    // ── Streaming cache (Settings → Storage) ─────────────────────────────────
    func loadCacheStats() async {
        guard canUseApi, !isLoadingCacheStats else { return }
        isLoadingCacheStats = true
        defer { isLoadingCacheStats = false }
        do {
            cacheStats = try await request("/tracks/cache/stats")
        } catch {
            if !isCancellation(error) { errorMessage = clean(error) }
        }
    }

    func clearStreamingCache() async {
        guard canUseApi, !isClearingCache else { return }
        isClearingCache = true
        defer { isClearingCache = false }
        do {
            cacheStats = try await request("/tracks/cache/cleanup", method: "POST")
        } catch {
            if !isCancellation(error) { errorMessage = clean(error) }
        }
    }

    // ── Per-user libraries ───────────────────────────────────────────────────
    func loadLibraries() async {
        guard canUseApi else { return }
        do {
            let response: LibraryListResponse = try await request("/libraries?limit=100")
            libraries = response.items
        } catch {
            if !isCancellation(error) { errorMessage = clean(error) }
        }
    }

    @discardableResult
    func createLibrary(name: String) async -> LibraryDetail? {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard canUseApi, !trimmed.isEmpty else { return nil }
        do {
            struct Body: Encodable { let name: String }
            let detail: LibraryDetail = try await request(
                "/libraries", method: "POST", body: try JSONEncoder().encode(Body(name: trimmed))
            )
            await loadLibraries()
            return detail
        } catch {
            if !isCancellation(error) { errorMessage = clean(error) }
            return nil
        }
    }

    func libraryDetail(_ id: String) async -> LibraryDetail? {
        guard canUseApi else { return nil }
        do {
            let encoded = encodePathComponent(id)
            return try await request("/libraries/\(encoded)")
        } catch {
            if !isCancellation(error) { errorMessage = clean(error) }
            return nil
        }
    }

    @discardableResult
    func addTrack(_ trackId: String, toLibrary libraryId: String) async -> LibraryDetail? {
        guard canUseApi else { return nil }
        do {
            struct Body: Encodable { let track_id: String }
            let encoded = encodePathComponent(libraryId)
            let detail: LibraryDetail = try await request(
                "/libraries/\(encoded)/tracks", method: "POST",
                body: try JSONEncoder().encode(Body(track_id: trackId))
            )
            await loadLibraries()
            return detail
        } catch {
            if !isCancellation(error) { errorMessage = clean(error) }
            return nil
        }
    }

    @discardableResult
    func removeTrack(_ trackId: String, fromLibrary libraryId: String) async -> LibraryDetail? {
        guard canUseApi else { return nil }
        do {
            let encodedLib = encodePathComponent(libraryId)
            let encodedTrack = encodePathComponent(trackId)
            let detail: LibraryDetail = try await request(
                "/libraries/\(encodedLib)/tracks/\(encodedTrack)", method: "DELETE"
            )
            await loadLibraries()
            return detail
        } catch {
            if !isCancellation(error) { errorMessage = clean(error) }
            return nil
        }
    }

    func deleteLibrary(_ id: String) async {
        guard canUseApi else { return }
        do {
            let encoded = encodePathComponent(id)
            let _: EmptyResponse = try await request("/libraries/\(encoded)", method: "DELETE")
            await loadLibraries()
        } catch {
            if !isCancellation(error) { errorMessage = clean(error) }
        }
    }

    func toggleLike(_ track: ApiTrack) async {
        let willLike = !likedTrackIds.contains(track.id)
        if willLike { likedTrackIds.insert(track.id) } else { likedTrackIds.remove(track.id) }
        rebuildDerivedLibraryState()
        do {
            let encodedId = encodePathComponent(track.id)
            let _: EmptyResponse = try await request("/tracks/\(encodedId)/like", method: willLike ? "PUT" : "DELETE")
        } catch {
            if willLike { likedTrackIds.remove(track.id) } else { likedTrackIds.insert(track.id) }
            rebuildDerivedLibraryState()
            if !isCancellation(error) { errorMessage = clean(error) }
        }
    }

    func isTrackAvailableOffline(_ track: ApiTrack) -> Bool {
        offlineTrackIds.contains(track.id)
    }

    func isAlbumAvailableOffline(_ album: Album) -> Bool {
        !album.tracks.isEmpty && album.tracks.allSatisfy { isTrackAvailableOffline($0) }
    }

    func downloadedTrackCount(in album: Album) -> Int {
        album.tracks.filter { isTrackAvailableOffline($0) }.count
    }

    func downloadTrack(_ track: ApiTrack) async {
        _ = await downloadTrackForOffline(track, announce: true)
    }

    func downloadAlbum(_ album: Album) async {
        guard !album.tracks.isEmpty else { return }
        if isAlbumAvailableOffline(album) {
            offlineStatusMessage = "\(album.title) is already available offline."
            return
        }

        downloadingAlbumIds.insert(album.id)
        defer { downloadingAlbumIds.remove(album.id) }

        var completed = 0
        for track in album.tracks {
            if await downloadTrackForOffline(track, announce: false) {
                completed += 1
                offlineStatusMessage = "Downloaded \(completed)/\(album.tracks.count) from \(album.title)."
            }
        }

        if completed == album.tracks.count {
            offlineStatusMessage = "\(album.title) is ready offline."
        } else if completed > 0 {
            offlineStatusMessage = "\(album.title): downloaded \(completed)/\(album.tracks.count)."
        }
    }

    func removeDownloadedTrack(_ track: ApiTrack) {
        do {
            guard try removeOfflineRecord(trackId: track.id) else {
                offlineStatusMessage = "\(track.title) is not downloaded."
                return
            }
            try writeOfflineRecords()
            stopPlaybackIfNeededAfterRemoving(trackIds: [track.id])
            refreshOfflineState()
            offlineStatusMessage = "Removed download for \(track.title)."
        } catch {
            errorMessage = "Could not remove download: \(clean(error))"
        }
    }

    func removeDownloadedAlbum(_ album: Album) {
        do {
            let removedIds = try album.tracks.reduce(into: Set<String>()) { ids, track in
                if try removeOfflineRecord(trackId: track.id) {
                    ids.insert(track.id)
                }
            }
            guard !removedIds.isEmpty else {
                offlineStatusMessage = "\(album.title) has no downloaded songs."
                return
            }
            try writeOfflineRecords()
            stopPlaybackIfNeededAfterRemoving(trackIds: removedIds)
            refreshOfflineState()
            offlineStatusMessage = "Removed \(removedIds.count) downloads from \(album.title)."
        } catch {
            errorMessage = "Could not remove album downloads: \(clean(error))"
        }
    }

    func removeAllDownloads() {
        do {
            let removedIds = Set(offlineRecords.keys)
            for trackId in removedIds {
                _ = try removeOfflineRecord(trackId: trackId)
            }
            try writeOfflineRecords()
            stopPlaybackIfNeededAfterRemoving(trackIds: removedIds)
            refreshOfflineState()
            offlineStatusMessage = "Removed all downloads."
        } catch {
            errorMessage = "Could not remove downloads: \(clean(error))"
        }
    }

    func createPlaylist(named name: String) async {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        guard canUseApi else {
            errorMessage = endpointWarning ?? "Set the API endpoint and log in in Settings."
            return
        }

        do {
            let body = try JSONEncoder().encode(PlaylistNamePayload(name: trimmed))
            let playlist: PlaylistDetail = try await request("/playlists", method: "POST", body: body)
            tracks = mergeTracks(existing: tracks, incoming: playlist.orderedTracks).sorted(by: stableLibraryTrackOrder)
            upsertPlaylist(playlist)
            selectedPlaylistId = playlist.id
            offlineStatusMessage = "Created playlist \(playlist.name)."
        } catch {
            if !isCancellation(error) { errorMessage = clean(error) }
        }
    }

    func deletePlaylist(_ playlist: PlaylistDetail) async {
        guard canUseApi else {
            errorMessage = endpointWarning ?? "Set the API endpoint and log in in Settings."
            return
        }
        do {
            let _: EmptyResponse = try await request("/playlists/\(encodePathComponent(playlist.id))", method: "DELETE")
            playlists.removeAll { $0.id == playlist.id }
            if selectedPlaylistId == playlist.id { selectedPlaylistId = nil }
            offlineStatusMessage = "Deleted playlist \(playlist.name)."
        } catch {
            if !isCancellation(error) { errorMessage = clean(error) }
        }
    }

    func addTrack(_ track: ApiTrack, to playlist: PlaylistDetail) async {
        guard canUseApi else {
            errorMessage = endpointWarning ?? "Set the API endpoint and log in in Settings."
            return
        }
        do {
            let body = try JSONEncoder().encode(PlaylistTrackPayload(trackId: track.id))
            let updated: PlaylistDetail = try await request(
                "/playlists/\(encodePathComponent(playlist.id))/tracks",
                method: "POST",
                body: body
            )
            tracks = mergeTracks(existing: tracks, incoming: updated.orderedTracks).sorted(by: stableLibraryTrackOrder)
            upsertPlaylist(updated)
            offlineStatusMessage = "Added \(track.title) to \(updated.name)."
        } catch {
            if !isCancellation(error) { errorMessage = clean(error) }
        }
    }

    func removeTrack(_ track: ApiTrack, from playlist: PlaylistDetail) async {
        guard canUseApi else {
            errorMessage = endpointWarning ?? "Set the API endpoint and log in in Settings."
            return
        }
        do {
            let updated: PlaylistDetail = try await request(
                "/playlists/\(encodePathComponent(playlist.id))/tracks/\(encodePathComponent(track.id))",
                method: "DELETE"
            )
            upsertPlaylist(updated)
            offlineStatusMessage = "Removed \(track.title) from \(updated.name)."
        } catch {
            if !isCancellation(error) { errorMessage = clean(error) }
        }
    }

    func deleteAlbum(_ album: Album) async {
        guard canUseApi else {
            errorMessage = endpointWarning ?? "Set the API endpoint and log in in Settings."
            return
        }
        isLoading = true
        defer { isLoading = false }
        errorMessage = nil

        var deletedIds = Set<String>()
        do {
            for track in album.tracks {
                let encodedId = encodePathComponent(track.id)
                let _: EmptyResponse = try await request("/tracks/\(encodedId)?delete_file=true", method: "DELETE")
                deletedIds.insert(track.id)
                _ = try? removeOfflineRecord(trackId: track.id)
            }
            try? writeOfflineRecords()
            tracks.removeAll { deletedIds.contains($0.id) }
            likedTrackIds.subtract(deletedIds)
            playbackQueue.removeAll { deletedIds.contains($0.id) }
            stopPlaybackIfNeededAfterRemoving(trackIds: deletedIds)
            refreshOfflineState()
            selectedAlbumId = nil
            offlineStatusMessage = "Deleted \(album.title)."
        } catch {
            if !deletedIds.isEmpty {
                tracks.removeAll { deletedIds.contains($0.id) }
                likedTrackIds.subtract(deletedIds)
                playbackQueue.removeAll { deletedIds.contains($0.id) }
                stopPlaybackIfNeededAfterRemoving(trackIds: deletedIds)
                refreshOfflineState()
            }
            if !isCancellation(error) { errorMessage = "Could not delete album: \(clean(error))" }
        }
    }

    @discardableResult
    private func downloadTrackForOffline(_ track: ApiTrack, announce: Bool) async -> Bool {
        if isTrackAvailableOffline(track) {
            if announce { offlineStatusMessage = "\(track.title) is already available offline." }
            return true
        }

        guard canUseApi else {
            errorMessage = endpointWarning ?? "Set the API endpoint and log in in Settings."
            return false
        }
        guard downloadOverCellularEnabled || !isConstrainedNetwork else {
            errorMessage = "Enable \u{201C}Download over cellular\u{201D} in Settings, or connect to Wi\u{2011}Fi, to download tracks."
            return false
        }
        let encodedId = encodePathComponent(track.id)
        guard let url = endpointURL(path: "/tracks/\(encodedId)/stream") else {
            errorMessage = "Bad API endpoint."
            return false
        }

        downloadingTrackIds.insert(track.id)
        defer { downloadingTrackIds.remove(track.id) }

        errorMessage = nil
        do {
            var request = URLRequest(url: url)
            request.timeoutInterval = 120
            request.setValue("Bearer \(apiToken)", forHTTPHeaderField: "Authorization")
            let (temporaryURL, response) = try await URLSession.shared.download(for: request)
            guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
                throw BackendError.message("Could not download track.")
            }

            let targetURL = try offlineTrackFileURL(for: track)
            try? FileManager.default.removeItem(at: targetURL)
            try FileManager.default.moveItem(at: temporaryURL, to: targetURL)
            try saveOfflineTrack(track, at: targetURL)
            if announce { offlineStatusMessage = "\(track.title) is ready offline." }
            return true
        } catch {
            if !isCancellation(error) { errorMessage = clean(error) }
            return false
        }
    }

    func play(_ track: ApiTrack, queue: [ApiTrack]? = nil, updateQueue: Bool = true, startAt startTime: TimeInterval? = nil) {
        if updateQueue {
            preparePlaybackQueue(for: track, from: queue ?? playbackContextTracks())
        }

        guard let source = playbackSource(for: track) else {
            errorMessage = isTrackAvailableOffline(track)
                ? "Downloaded file is missing from this device."
                : "Track is not downloaded and the backend is not reachable/configured."
            return
        }

        configureAudioSession()
        removePlaybackItemObservers()
        removeTimeObserver()
        removePlayerStateObserver()
        player?.pause()
        isRecoveringPlayback = false
        isAwaitingReconnectToResume = false

        let asset: AVURLAsset
        if let headers = source.headers {
            asset = AVURLAsset(url: source.url, options: ["AVURLAssetHTTPHeaderFieldsKey": headers])
        } else {
            asset = AVURLAsset(url: source.url)
        }
        let item = AVPlayerItem(asset: asset)
        let nextPlayer = AVPlayer(playerItem: item)
        addPlaybackItemObservers(to: item, track: track)

        player = nextPlayer
        currentTrack = track
        currentCodecBadge = codecBadge(for: track, playingOffline: localOfflineFileURL(for: track) != nil)
        savedPlaybackTrackId = track.id
        let elapsed = normalizedPlaybackStartTime(startTime, for: track)
        savedPlaybackElapsedTime = elapsed
        playbackProgress = playbackProgress(for: elapsed, in: track)
        beginPlaySession(for: track, startingAt: elapsed)
        addTimeObserver(to: nextPlayer)
        observePlayerState(nextPlayer)
        if elapsed > 0 {
            nextPlayer.seek(to: CMTime(seconds: elapsed, preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero)
        }
        nextPlayer.play()
        isPlaying = true
        updateNowPlayingInfo(for: track, elapsed: elapsed)
        syncPlaybackSideEffects(for: track)
        scheduleAutoplayPrefetchIfNeeded(for: track)
    }

    /// Registers the "track ended" observer plus the stall/failure observers that drive seamless
    /// recovery when the network drops mid-stream (see `handlePlaybackInterruption`).
    private func addPlaybackItemObservers(to item: AVPlayerItem, track: ApiTrack) {
        playerItemEndObserver = NotificationCenter.default.addObserver(
            forName: .AVPlayerItemDidPlayToEndTime,
            object: item,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor in
                self?.finalizePlaySession(naturalEnd: true)
                self?.nextTrack()
            }
        }
        playerItemStalledObserver = NotificationCenter.default.addObserver(
            forName: .AVPlayerItemPlaybackStalled,
            object: item,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor in await self?.handlePlaybackInterruption(for: track) }
        }
        playerItemFailedObserver = NotificationCenter.default.addObserver(
            forName: .AVPlayerItemFailedToPlayToEndTime,
            object: item,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor in await self?.handlePlaybackInterruption(for: track) }
        }
    }

    private func removePlaybackItemObservers() {
        removePlayerItemEndObserver()
        if let playerItemStalledObserver {
            NotificationCenter.default.removeObserver(playerItemStalledObserver)
        }
        playerItemStalledObserver = nil
        if let playerItemFailedObserver {
            NotificationCenter.default.removeObserver(playerItemFailedObserver)
        }
        playerItemFailedObserver = nil
    }

    func togglePlayback() {
        guard let player else {
            if let currentTrack {
                let startTime = savedStartTime(for: currentTrack)
                play(currentTrack, updateQueue: false, startAt: startTime)
            }
            return
        }
        if isPlaying {
            saveCurrentPlaybackPosition()
            player.pause()
            isPlaying = false
        } else {
            configureAudioSession()
            player.play()
            isPlaying = true
        }
        updateNowPlayingPlaybackRate()
        Task { await postPlaybackState() }
    }

    func nextTrack() {
        guard let currentTrack else {
            if let first = queueTracks.first { play(first, queue: queueTracks, updateQueue: false) }
            return
        }

        if repeatMode == .one {
            play(currentTrack, updateQueue: false)
            return
        }

        let list = queueTracks
        guard !list.isEmpty else { return }
        guard let index = list.firstIndex(where: { $0.id == currentTrack.id }) else {
            play(list[0], queue: list, updateQueue: false)
            return
        }

        let nextIndex = list.index(after: index)
        if nextIndex < list.endIndex {
            play(list[nextIndex], queue: list, updateQueue: false)
        } else if repeatMode == .all, let first = list.first {
            play(first, queue: list, updateQueue: false)
        } else {
            // Prefer the backend radio continuation prefetched while this track played;
            // a stale stash (different seed) is discarded, and offline/failed prefetch
            // falls back to the on-device heuristic.
            let stashed = autoplayStashSeedId == currentTrack.id
                ? autoplayStash.filter { candidate in !list.contains { $0.id == candidate.id } }
                : []
            autoplayStash = []
            autoplayStashSeedId = nil
            let recommendations: [ApiTrack]
            if !autoplaySimilarEnabled {
                recommendations = []
            } else if !stashed.isEmpty {
                recommendations = stashed
            } else {
                recommendations = autoplayRecommendations(after: currentTrack, excluding: list)
            }
            if let first = recommendations.first {
                play(first, queue: list + recommendations, updateQueue: false)
                return
            }

            player?.pause()
            isPlaying = false
            playbackProgress = 1
            updateNowPlayingPlaybackRate()
        }
    }

    func previousTrack() {
        guard let currentTrack else {
            if let first = queueTracks.first { play(first, queue: queueTracks, updateQueue: false) }
            return
        }

        let list = queueTracks
        guard !list.isEmpty else { return }
        guard let index = list.firstIndex(where: { $0.id == currentTrack.id }) else {
            play(list[0], queue: list, updateQueue: false)
            return
        }

        if index > list.startIndex {
            play(list[list.index(before: index)], queue: list, updateQueue: false)
        } else if repeatMode == .all, let last = list.last {
            play(last, queue: list, updateQueue: false)
        } else {
            play(currentTrack, updateQueue: false)
        }
    }

    func toggleShuffle() {
        shuffleEnabled.toggle()
        guard let currentTrack else {
            let context = playbackContextTracks()
            playbackQueue = shuffleEnabled ? context.shuffled() : context
            Task { await postPlaybackState() }
            return
        }
        preparePlaybackQueue(for: currentTrack, from: playbackQueue.isEmpty ? playbackContextTracks() : playbackQueue)
        schedulePlaybackPrefetch()
        Task { await postPlaybackState() }
    }

    func cycleRepeatMode() {
        switch repeatMode {
        case .off:
            repeatMode = .all
        case .all:
            repeatMode = .one
        case .one:
            repeatMode = .off
        }
        if repeatMode != .off {
            // A repeating queue never runs out, so a prefetched radio continuation is moot.
            autoplayPrefetchTask?.cancel()
            autoplayStash = []
            autoplayStashSeedId = nil
        } else if let currentTrack {
            scheduleAutoplayPrefetchIfNeeded(for: currentTrack)
        }
        Task { await postPlaybackState() }
    }

    func addToQueue(_ track: ApiTrack) {
        if playbackQueue.isEmpty, let currentTrack {
            playbackQueue = [currentTrack]
        }
        guard !playbackQueue.contains(where: { $0.id == track.id }) else { return }
        playbackQueue.append(track)
        schedulePlaybackPrefetch()
        Task { await postPlaybackState() }
    }

    func removeFromQueue(_ track: ApiTrack) {
        guard currentTrack?.id != track.id else { return }
        playbackQueue.removeAll { $0.id == track.id }
        schedulePlaybackPrefetch()
        Task { await postPlaybackState() }
    }

    func clearQueue() {
        playbackQueue = currentTrack.map { [$0] } ?? []
        schedulePlaybackPrefetch()
        Task { await postPlaybackState() }
    }

    private func loadAllTracks() async throws -> [ApiTrack] {
        var items: [ApiTrack] = []
        let limit = 200
        var offset = 0
        while true {
            let response: TrackListResponse = try await request("/tracks?limit=\(limit)&offset=\(offset)")
            items.append(contentsOf: response.items)
            if response.items.count < limit { break }
            offset += limit
        }
        return items
    }

    private func loadAllLikedTrackIds() async throws -> Set<String> {
        var ids = Set<String>()
        let limit = 200
        var offset = 0
        while true {
            let response: LikedTracksResponse = try await request("/tracks/liked?limit=\(limit)&offset=\(offset)")
            ids.formUnion(response.items.map { $0.track.id })
            if response.items.count < limit { break }
            offset += limit
        }
        return ids
    }

    private func loadAllPlaylists() async throws -> [PlaylistDetail] {
        var summaries: [PlaylistSummary] = []
        let limit = 100
        var offset = 0
        while true {
            let response: PlaylistListResponse = try await request("/playlists?limit=\(limit)&offset=\(offset)")
            summaries.append(contentsOf: response.items)
            if response.items.count < limit { break }
            offset += limit
        }

        // Fetch every playlist's detail concurrently instead of one-at-a-time: this used to be
        // a sequential N+1 (one round trip per playlist) that dominated cold-start latency for
        // libraries with many playlists.
        let orderedSummaries = summaries.sorted(by: playlistSummaryOrder)
        let detailsById = try await withThrowingTaskGroup(of: (String, PlaylistDetail).self) { group in
            for summary in orderedSummaries {
                group.addTask {
                    let detail: PlaylistDetail = try await self.request("/playlists/\(self.encodePathComponent(summary.id))")
                    return (summary.id, detail)
                }
            }
            var results: [String: PlaylistDetail] = [:]
            for try await (id, detail) in group {
                results[id] = detail
            }
            return results
        }
        return orderedSummaries.compactMap { detailsById[$0.id] }
    }

    private func remapPlaylists(_ incoming: [PlaylistDetail]) -> [PlaylistDetail] {
        let byId = Dictionary(uniqueKeysWithValues: tracks.map { ($0.id, $0) })
        return incoming
            .map { playlist in
                PlaylistDetail(
                    id: playlist.id,
                    name: playlist.name,
                    tracks: playlist.tracks.map { item in
                        PlaylistTrackItem(
                            position: item.position,
                            addedAt: item.addedAt,
                            track: byId[item.track.id] ?? item.track
                        )
                    },
                    createdAt: playlist.createdAt,
                    updatedAt: playlist.updatedAt
                )
            }
            .sorted(by: playlistDetailOrder)
    }

    private func upsertPlaylist(_ playlist: PlaylistDetail) {
        let remapped = remapPlaylists([playlist])[0]
        if let index = playlists.firstIndex(where: { $0.id == remapped.id }) {
            playlists[index] = remapped
        } else {
            playlists.append(remapped)
        }
        playlists.sort(by: playlistDetailOrder)
    }

    /// Fetches the play-history feed that powers the recently-played grid, "Recents", and
    /// "Jump back in" shelves. Returns nil on failure so callers keep the cached feed.
    private func loadRecentPlays() async -> [RecentPlayPayload]? {
        guard canUseApi else { return nil }
        do {
            let response: RecentPlaysResponse = try await request("/tracks/recent?limit=60")
            return response.items
        } catch {
            return nil
        }
    }

    private func loadPersonalizedHome(silent: Bool = true) async {
        guard canUseApi else {
            backendRecommendedTrackIds = []
            backendDailyMixes = []
            rebuildDerivedLibraryState()
            return
        }

        do {
            let response: PersonalizedHomeResponse = try await request(
                "/recommendations/personalized?local_limit=24&mix_count=4&mix_size=12"
            )
            let receivedTracks = response.recommendedTracks.map(\.track)
                + response.dailyMixes.flatMap { $0.tracks.map(\.track) }
            if !receivedTracks.isEmpty {
                tracks = mergeTracks(existing: tracks, incoming: receivedTracks).sorted(by: stableLibraryTrackOrder)
            }
            backendRecommendedTrackIds = response.recommendedTracks.map { $0.track.id }
            backendDailyMixes = response.dailyMixes.map { mix in
                DailyMix(
                    id: mix.id,
                    title: mix.title,
                    description: mix.description,
                    seedLabel: mix.seedLabel,
                    tracks: mix.tracks.map(\.track)
                )
            }
            lastPersonalizationRefreshAt = Date()
            rebuildDerivedLibraryState()
        } catch {
            backendRecommendedTrackIds = []
            backendDailyMixes = []
            rebuildDerivedLibraryState()
            if !silent, !isCancellation(error) { errorMessage = clean(error) }
        }
    }

    private func searchLegacyTorrentSources(encodedQuery: String) async throws -> [TorrentResult] {
        async let pirateBaySearch = torrentSearchResult(source: .pirateBay, encodedQuery: encodedQuery)
        async let thirteenThirtySevenSearch = torrentSearchResult(source: .thirteenThirtySevenX, encodedQuery: encodedQuery)
        let searchResults = await [pirateBaySearch, thirteenThirtySevenSearch]
        let items = searchResults.flatMap { result -> [TorrentResult] in
            guard case let .success(items) = result else { return [] }
            return items
        }

        if items.isEmpty, let failure = searchResults.first(where: { result in
            if case .failure = result { return true }
            return false
        }) {
            if case let .failure(error) = failure { throw error }
        }

        return items
    }

    private func torrentSearchResult(source: TorrentSource, encodedQuery: String) async -> Result<[TorrentResult], Error> {
        do {
            var path = "\(source.searchPath)?q=\(encodedQuery)"
            if source == .thirteenThirtySevenX {
                path += "&sort_by=seeders"
            }
            let response: TorrentSearchResponse = try await request(path)
            return .success(response.items.map { $0.withSource(source) })
        } catch {
            return .failure(error)
        }
    }

    private func mergeTracks(existing: [ApiTrack], incoming: [ApiTrack]) -> [ApiTrack] {
        var merged = Dictionary(uniqueKeysWithValues: existing.map { ($0.id, $0) })
        for track in incoming { merged[track.id] = track }
        return Array(merged.values)
    }

    private func loadOfflineLibrary() {
        do {
            let records = try readOfflineRecords().filter { record in
                offlineFileURL(relativePath: record.relativePath).map { FileManager.default.fileExists(atPath: $0.path) } ?? false
            }
            offlineRecords = Dictionary(uniqueKeysWithValues: records.map { ($0.track.id, $0) })
            // With no offline downloads there's nothing to merge into the library, so skip the
            // expensive derived-state rebuild the snapshot load already did — this used to double
            // the cold-start cost by recomputing albums/recommendations/mixes a second time.
            guard !records.isEmpty else { return }
            tracks = mergeTracks(existing: tracks, incoming: records.map(\.track)).sorted(by: stableLibraryTrackOrder)
            refreshOfflineState()
            offlineStatusMessage = "Offline library ready: \(records.count) downloaded songs."
        } catch {
            offlineStatusMessage = "Could not load offline library: \(clean(error))"
        }
    }

    /// Last-known-good snapshot of the library, persisted to disk so the app can render real
    /// content on the very first frame instead of an empty state while `refreshLibrary()`'s
    /// network calls are still in flight.
    private func loadCachedLibrarySnapshot() {
        do {
            guard let data = try? Data(contentsOf: librarySnapshotURL()) else { return }
            let decoder = JSONDecoder()
            let snapshot = try decoder.decode(LibrarySnapshot.self, from: data)
            tracks = mergeTracks(existing: tracks, incoming: snapshot.tracks).sorted(by: stableLibraryTrackOrder)
            likedTrackIds = snapshot.likedTrackIds
            playlists = remapPlaylists(snapshot.playlists)
            recentPlayEvents = snapshot.recentPlays ?? []
            rebuildDerivedLibraryState()
            syncQueueWithLibrary()
            restorePlaybackStateIfNeeded()
        } catch {
            // A missing/corrupt snapshot just means a normal cold start; refreshLibrary() will
            // populate everything from the network as before.
        }
    }

    private func persistLibrarySnapshot() {
        let snapshot = LibrarySnapshot(
            tracks: tracks,
            likedTrackIds: likedTrackIds,
            playlists: playlists,
            recentPlays: Array(recentPlayEvents.prefix(60))
        )
        Task.detached(priority: .utility) {
            do {
                let encoder = JSONEncoder()
                let data = try encoder.encode(snapshot)
                let url = try await self.librarySnapshotURL()
                try data.write(to: url, options: .atomic)
            } catch {
                // Best-effort cache write; a failure here only costs the next cold start its
                // instant-hydrate, refreshLibrary() remains the source of truth.
            }
        }
    }

    private func librarySnapshotURL() throws -> URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("MekambMusic", isDirectory: true)
            .appendingPathComponent("LibraryCache", isDirectory: true)
        try FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        var mutableBase = base
        try? mutableBase.setResourceValues(values)
        return base.appendingPathComponent("library-snapshot.json", isDirectory: false)
    }

    private func saveOfflineTrack(_ track: ApiTrack, at fileURL: URL) throws {
        let relativePath = fileURL.lastPathComponent
        let attributes = try? FileManager.default.attributesOfItem(atPath: fileURL.path)
        let size = attributes?[.size] as? Int ?? track.sizeBytes
        offlineRecords[track.id] = OfflineTrackRecord(
            track: track,
            relativePath: relativePath,
            downloadedAt: Date(),
            sizeBytes: size
        )
        try writeOfflineRecords()
        tracks = mergeTracks(existing: tracks, incoming: [track]).sorted(by: stableLibraryTrackOrder)
        syncQueueWithLibrary()
        refreshOfflineState()
    }

    private func removeOfflineRecord(trackId: String) throws -> Bool {
        guard let record = offlineRecords.removeValue(forKey: trackId) else { return false }
        if let url = offlineFileURL(relativePath: record.relativePath),
           FileManager.default.fileExists(atPath: url.path) {
            try FileManager.default.removeItem(at: url)
        }
        return true
    }

    private func stopPlaybackIfNeededAfterRemoving(trackIds: Set<String>) {
        guard let currentTrack, trackIds.contains(currentTrack.id) else { return }
        player?.pause()
        isPlaying = false
        updateNowPlayingPlaybackRate()
    }

    private func refreshOfflineState() {
        let existingRecords = offlineRecords.values.filter { record in
            offlineFileURL(relativePath: record.relativePath).map { FileManager.default.fileExists(atPath: $0.path) } ?? false
        }
        if existingRecords.count != offlineRecords.count {
            offlineRecords = Dictionary(uniqueKeysWithValues: existingRecords.map { ($0.track.id, $0) })
            try? writeOfflineRecords()
        }
        offlineTrackIds = Set(existingRecords.map(\.track.id))
        offlineStorageBytes = existingRecords.reduce(0) { total, record in
            guard let url = offlineFileURL(relativePath: record.relativePath),
                  let attributes = try? FileManager.default.attributesOfItem(atPath: url.path),
                  let size = attributes[.size] as? Int else {
                return total + (record.sizeBytes ?? 0)
            }
            return total + size
        }
        rebuildDerivedLibraryState()
    }

    private func readOfflineRecords() throws -> [OfflineTrackRecord] {
        let url = try offlineMetadataURL()
        guard FileManager.default.fileExists(atPath: url.path) else { return [] }
        let data = try Data(contentsOf: url)
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try decoder.decode([OfflineTrackRecord].self, from: data)
    }

    private func writeOfflineRecords() throws {
        let url = try offlineMetadataURL()
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let records = offlineRecords.values.sorted {
            stableLibraryTrackOrder($0.track, $1.track)
        }
        let data = try encoder.encode(records)
        try data.write(to: url, options: .atomic)
    }

    private func playbackSource(for track: ApiTrack) -> PlaybackSource? {
        if let localURL = localOfflineFileURL(for: track) {
            return PlaybackSource(url: localURL, headers: nil)
        }
        if let cachedURL = localPlaybackCacheFileURL(for: track) {
            return PlaybackSource(url: cachedURL, headers: nil)
        }

        guard canUseApi else { return nil }
        let encodedId = encodePathComponent(track.id)
        let query = streamFormatParam(for: track) == "aac" ? "?format=aac" : ""
        guard let url = endpointURL(path: "/tracks/\(encodedId)/stream\(query)") else { return nil }
        return PlaybackSource(url: url, headers: ["Authorization": "Bearer \(apiToken)"])
    }

    /// Whether the current quality setting + connection want an AAC stream (before considering the
    /// source format).
    private var wantsAacStream: Bool {
        switch playbackQuality {
        case .lossless: return false
        case .aac: return true
        case .auto: return isConstrainedNetwork
        }
    }

    private static let losslessExtensions: Set<String> = ["flac", "wav", "wave", "aif", "aiff", "alac", "ape", "wv"]

    private func sourceExtension(for track: ApiTrack) -> String {
        let fromName = URL(fileURLWithPath: track.originalFilename ?? "").pathExtension.lowercased()
        if !fromName.isEmpty { return fromName }
        switch (track.mediaType ?? "").lowercased() {
        case "audio/flac", "audio/x-flac": return "flac"
        case "audio/wav", "audio/x-wav", "audio/wave": return "wav"
        case "audio/aiff", "audio/x-aiff": return "aiff"
        case "audio/mpeg": return "mp3"
        case "audio/mp4", "audio/aac", "audio/x-m4a": return "m4a"
        case "audio/ogg": return "ogg"
        default: return ""
        }
    }

    private func isLosslessSource(_ track: ApiTrack) -> Bool {
        Self.losslessExtensions.contains(sourceExtension(for: track))
    }

    /// The `format` query value to request for this track: only lossless sources get transcoded to
    /// AAC — lossy sources are already compact and are always served as-is.
    private func streamFormatParam(for track: ApiTrack) -> String? {
        (wantsAacStream && isLosslessSource(track)) ? "aac" : nil
    }

    /// Short codec label to show next to the playing track.
    private func codecBadge(for track: ApiTrack, playingOffline: Bool) -> String {
        if !playingOffline, streamFormatParam(for: track) == "aac" { return "AAC" }
        switch sourceExtension(for: track) {
        case "flac": return "FLAC"
        case "wav", "wave": return "WAV"
        case "aif", "aiff": return "AIFF"
        case "alac": return "ALAC"
        case "mp3": return "MP3"
        case "m4a", "aac", "mp4": return "AAC"
        case "ogg", "opus": return sourceExtension(for: track).uppercased()
        case "": return "AUDIO"
        default: return sourceExtension(for: track).uppercased()
        }
    }

    private func localOfflineFileURL(for track: ApiTrack) -> URL? {
        guard let record = offlineRecords[track.id] else { return nil }
        guard let url = offlineFileURL(relativePath: record.relativePath),
              FileManager.default.fileExists(atPath: url.path) else { return nil }
        return url
    }

    private func localPlaybackCacheFileURL(for track: ApiTrack) -> URL? {
        guard let url = try? playbackCacheFileURL(for: track),
              FileManager.default.fileExists(atPath: url.path),
              ((try? FileManager.default.attributesOfItem(atPath: url.path)[.size] as? Int) ?? 0) > 0 else {
            return nil
        }
        return url
    }

    private func offlineTrackFileURL(for track: ApiTrack) throws -> URL {
        try offlineTracksDirectory().appendingPathComponent(offlineFileName(for: track), isDirectory: false)
    }

    private func offlineFileURL(relativePath: String) -> URL? {
        try? offlineTracksDirectory().appendingPathComponent(relativePath, isDirectory: false)
    }

    private func offlineMetadataURL() throws -> URL {
        try offlineRootDirectory().appendingPathComponent("offline-library.json", isDirectory: false)
    }

    private func offlineTracksDirectory() throws -> URL {
        let url = try offlineRootDirectory().appendingPathComponent("tracks", isDirectory: true)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }

    private func offlineRootDirectory() throws -> URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("MekambMusic", isDirectory: true)
            .appendingPathComponent("Offline", isDirectory: true)
        try FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        var mutableBase = base
        try? mutableBase.setResourceValues(values)
        return base
    }

    private func playbackCacheFileURL(for track: ApiTrack) throws -> URL {
        // Namespace the cache by requested format so an AAC copy and a lossless copy never collide.
        let prefix = streamFormatParam(for: track) == "aac" ? "aac-" : ""
        return try playbackCacheDirectory().appendingPathComponent("\(prefix)\(offlineFileName(for: track))", isDirectory: false)
    }

    private func playbackCacheDirectory() throws -> URL {
        let base = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("MekambMusic", isDirectory: true)
            .appendingPathComponent("PlaybackCache", isDirectory: true)
        try FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        return base
    }

    private func offlineFileName(for track: ApiTrack) -> String {
        let sourceExtension = URL(fileURLWithPath: downloadFilename(for: track)).pathExtension
        let extensionName = sourceExtension.isEmpty ? "audio" : sourceExtension
        return "\(safeFileComponent(track.id)).\(extensionName)"
    }

    private func safeFileComponent(_ value: String) -> String {
        let cleaned = value.replacingOccurrences(
            of: #"[^A-Za-z0-9._-]+"#,
            with: "_",
            options: .regularExpression
        )
        return cleaned.trimmingCharacters(in: CharacterSet(charactersIn: "._-")).isEmpty ? UUID().uuidString : cleaned
    }

    private func playbackContextTracks() -> [ApiTrack] {
        if selectedTab == .albums, let selectedAlbum { return selectedAlbum.tracks }
        if selectedTab == .playlists, let selectedPlaylist { return selectedPlaylist.orderedTracks }
        let context = filteredTracks
        return context.isEmpty ? tracks : context
    }

    private func preparePlaybackQueue(for track: ApiTrack, from candidates: [ApiTrack]) {
        var seen = Set<String>()
        var unique = candidates.filter { candidate in
            guard !seen.contains(candidate.id) else { return false }
            seen.insert(candidate.id)
            return true
        }
        if !unique.contains(where: { $0.id == track.id }) {
            unique.insert(track, at: 0)
        }

        if shuffleEnabled {
            let rest = unique.filter { $0.id != track.id }.shuffled()
            playbackQueue = [track] + rest
        } else {
            playbackQueue = unique
        }
    }

    private func autoplayRecommendations(after track: ApiTrack, excluding queue: [ApiTrack]) -> [ApiTrack] {
        let excludedIds = Set(queue.map(\.id))
        let candidates = tracks.filter { candidate in
            candidate.id != track.id && !excludedIds.contains(candidate.id)
        }
        guard !candidates.isEmpty else { return [] }

        let scored = candidates.map { candidate in
            (track: candidate, score: similarityScore(candidate, to: track))
        }
        let similar = scored
            .filter { $0.score > 0 }
            .sorted { left, right in
                if left.score != right.score { return left.score > right.score }
                return stableLibraryTrackOrder(left.track, right.track)
            }
            .map(\.track)

        if !similar.isEmpty {
            return Array(similar.prefix(25))
        }

        return Array(candidates.sorted(by: stableLibraryTrackOrder).prefix(25))
    }

    private func similarityScore(_ candidate: ApiTrack, to track: ApiTrack) -> Int {
        var score = 0
        if let candidateArtist = normalizedGroupingValue(candidate.artist),
           let trackArtist = normalizedGroupingValue(track.artist),
           candidateArtist == trackArtist {
            score += 6
        }
        if let candidateAlbum = normalizedGroupingValue(candidate.album),
           let trackAlbum = normalizedGroupingValue(track.album),
           candidateAlbum == trackAlbum {
            score += 4
        }
        if likedTrackIds.contains(candidate.id) {
            score += 1
        }

        let sharedTitleTokens = titleTokens(candidate.title).intersection(titleTokens(track.title)).count
        return score + min(sharedTitleTokens, 2)
    }

    private func localDailyMixScore(_ candidate: ApiTrack, seedTracks: [ApiTrack], salt: String) -> Int {
        let seedScore = seedTracks.map { similarityScore(candidate, to: $0) }.max() ?? 0
        let likedBoost = likedTrackIds.contains(candidate.id) ? 4 : 0
        let offlineBoost = offlineTrackIds.contains(candidate.id) ? 1 : 0
        let randomBoost = Int(stableShuffleScore(for: candidate.id, salt: dailyRecommendationSalt + "|\(salt)") % 8)
        return seedScore + likedBoost + offlineBoost + randomBoost
    }

    private func dailyStableTrackOrder(salt: String) -> (ApiTrack, ApiTrack) -> Bool {
        { [self] left, right in
            let leftScore = self.stableShuffleScore(for: left.id, salt: self.dailyRecommendationSalt + "|\(salt)")
            let rightScore = self.stableShuffleScore(for: right.id, salt: self.dailyRecommendationSalt + "|\(salt)")
            if leftScore != rightScore { return leftScore > rightScore }
            return self.stableLibraryTrackOrder(left, right)
        }
    }

    private var dailyRecommendationSalt: String {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: Date())
    }

    private func stableShuffleScore(for value: String, salt: String) -> UInt64 {
        var hash: UInt64 = 1_469_598_103_934_665_603
        for byte in "\(salt)|\(value)".utf8 {
            hash ^= UInt64(byte)
            hash = hash &* 1_099_511_628_211
        }
        return hash
    }

    private func titleTokens(_ title: String) -> Set<String> {
        let separators = CharacterSet.alphanumerics.inverted
        return Set(title
            .lowercased()
            .components(separatedBy: separators)
            .filter { $0.count > 3 })
    }

    private func syncQueueWithLibrary() {
        guard !playbackQueue.isEmpty else { return }
        let byId = Dictionary(uniqueKeysWithValues: tracks.map { ($0.id, $0) })
        playbackQueue = playbackQueue.compactMap { byId[$0.id] ?? $0 }
    }

    private func restorePlaybackStateIfNeeded() {
        guard !didRestorePlaybackState else {
            if currentTrack == nil { currentTrack = tracks.first }
            return
        }

        didRestorePlaybackState = true
        guard let restoredTrack = tracks.first(where: { $0.id == savedPlaybackTrackId }) else {
            if currentTrack == nil { currentTrack = tracks.first }
            return
        }

        currentTrack = restoredTrack
        playbackQueue = tracks
        let elapsed = normalizedPlaybackStartTime(savedPlaybackElapsedTime, for: restoredTrack)
        savedPlaybackElapsedTime = elapsed
        playbackProgress = playbackProgress(for: elapsed, in: restoredTrack)
        updateNowPlayingInfo(for: restoredTrack, elapsed: elapsed)
    }

    private func savedStartTime(for track: ApiTrack) -> TimeInterval {
        guard track.id == savedPlaybackTrackId else { return 0 }
        return normalizedPlaybackStartTime(savedPlaybackElapsedTime, for: track)
    }

    private func saveCurrentPlaybackPosition(elapsed: TimeInterval? = nil) {
        guard let currentTrack else { return }
        let currentElapsed = elapsed ?? currentElapsedTime()
        savedPlaybackTrackId = currentTrack.id
        savedPlaybackElapsedTime = normalizedPlaybackStartTime(currentElapsed, for: currentTrack)
    }

    private func normalizedPlaybackStartTime(_ seconds: TimeInterval?, for track: ApiTrack) -> TimeInterval {
        guard let seconds, seconds.isFinite, seconds > 0 else { return 0 }
        guard let duration = track.durationSeconds, duration.isFinite, duration > 0 else { return seconds }
        return seconds >= max(duration - 3, 0) ? 0 : min(seconds, duration)
    }

    private func playbackProgress(for elapsed: TimeInterval, in track: ApiTrack) -> Double {
        guard let duration = track.durationSeconds, duration.isFinite, duration > 0 else { return 0 }
        return min(max(elapsed / duration, 0), 1)
    }

    private func postPlay(_ track: ApiTrack, completed: Bool, listenRatio: Double?) async throws {
        guard canUseApi else { return }
        let encodedId = encodePathComponent(track.id)
        let body = try JSONEncoder().encode(
            PlaybackEventBody(completed: completed, listenRatio: listenRatio, source: "ios")
        )
        let _: EmptyResponse = try await request("/tracks/\(encodedId)/plays", method: "POST", body: body)
        if lastPersonalizationRefreshAt.map({ Date().timeIntervalSince($0) > 60 }) ?? true {
            await loadPersonalizedHome()
        }
    }

    /// Starts a listening session for the track that just began playing. Restarting the same
    /// track (pause/resume, repeat-one, previous-at-start) keeps the current session so it
    /// isn't miscounted as a skip.
    private func beginPlaySession(for track: ApiTrack, startingAt elapsed: TimeInterval) {
        if playSession?.track.id == track.id { return }
        finalizePlaySession()
        playSession = (track: track, maxElapsed: elapsed)
    }

    /// Reports the outgoing track's real listening outcome to the backend. Uses the session's
    /// max elapsed position (not the final one) so seeking back near the end doesn't turn a
    /// full listen into a skip. completed=false with a low listen_ratio is what the backend
    /// records as a skip signal for personalization.
    private func finalizePlaySession(naturalEnd: Bool = false) {
        guard let session = playSession else { return }
        playSession = nil
        var ratio: Double?
        if let duration = session.track.durationSeconds, duration.isFinite, duration > 0 {
            ratio = min(max(session.maxElapsed / duration, 0), 1)
        }
        if naturalEnd { ratio = 1.0 }
        let completed = naturalEnd || (ratio ?? 0) >= 0.9
        Task { try? await postPlay(session.track, completed: completed, listenRatio: ratio) }
    }

    private func syncPlaybackSideEffects(for track: ApiTrack) {
        schedulePlaybackPrefetch()
        scheduleCurrentTrackBackgroundCache(track)
        recordLocalRecentPlay(track)
        Task {
            await postPlaybackState()
        }
    }

    /// Optimistically prepends the started track to the local play-history feed so the
    /// recently-played shelves update instantly; the authoritative feed comes back from
    /// GET /tracks/recent on the next library refresh. Only the play-history shelves are
    /// rebuilt — a full rebuildDerivedLibraryState() on every track change is needless work.
    private func recordLocalRecentPlay(_ track: ApiTrack) {
        let timestamp = ISO8601DateFormatter().string(from: Date())
        recentPlayEvents.insert(
            RecentPlayPayload(track: track, playedAt: timestamp, completed: nil, listenRatio: nil),
            at: 0
        )
        if recentPlayEvents.count > 120 {
            recentPlayEvents.removeLast(recentPlayEvents.count - 120)
        }
        let tracksById = Dictionary(uniqueKeysWithValues: tracks.map { ($0.id, $0) })
        rebuildPlayHistoryShelves(rebuiltAlbums: albums, tracksById: tracksById)
    }

    /// Prefetches the backend radio continuation while the LAST queued track plays, so the
    /// hand-off at queue end is a synchronous, gapless queue extension in nextTrack().
    /// Starting any track that is not last — or with repeat on — invalidates the stash,
    /// because the queue can no longer run out from that track.
    private func scheduleAutoplayPrefetchIfNeeded(for track: ApiTrack) {
        guard autoplaySimilarEnabled, repeatMode == .off, canUseApi,
              !queueTracks.isEmpty, upcomingQueueTracks.isEmpty else {
            autoplayPrefetchTask?.cancel()
            autoplayStash = []
            autoplayStashSeedId = nil
            return
        }
        guard autoplayStashSeedId != track.id || autoplayStash.isEmpty else { return }

        autoplayPrefetchTask?.cancel()
        autoplayPrefetchTask = Task { [weak self] in
            await self?.prefetchAutoplayContinuation(seed: track)
        }
    }

    private func prefetchAutoplayContinuation(seed: ApiTrack) async {
        // The backend also excludes its own recent-plays window, so capping the client-sent
        // exclude list keeps the URL small even when the queue is the whole library.
        let excludeIds = queueTracks.suffix(100).map(\.id).joined(separator: ",")
        let encodedSeed = encodePathComponent(seed.id)
        let encodedExclude = excludeIds.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? excludeIds
        do {
            let response: AutoplayQueuePayload = try await request(
                "/recommendations/autoplay?seed_track_id=\(encodedSeed)&exclude=\(encodedExclude)&limit=25"
            )
            guard !Task.isCancelled, currentTrack?.id == seed.id else { return }
            let fetched = response.tracks.map(\.track)
            guard !fetched.isEmpty else { return }
            tracks = mergeTracks(existing: tracks, incoming: fetched).sorted(by: stableLibraryTrackOrder)
            let queueIds = Set(queueTracks.map(\.id))
            autoplayStash = fetched.filter { !queueIds.contains($0.id) }
            autoplayStashSeedId = seed.id
        } catch {
            // Offline or backend error — nextTrack() falls back to the local heuristic.
        }
    }

    /// While a track streams live, also download it to the playback cache in the background so a
    /// network drop later in the song has a local copy to fall back to. No-ops once the track is
    /// already offline or already cached (`cacheTrackToPlaybackDisk` checks both). Runs on both
    /// Wi-Fi and cellular — reliability was chosen over saving cellular data for this app.
    private func scheduleCurrentTrackBackgroundCache(_ track: ApiTrack) {
        currentTrackCacheTask?.cancel()
        currentTrackCacheTask = Task { [weak self] in
            await self?.cacheTrackToPlaybackDisk(track)
        }
    }

    private func startNetworkMonitoring() {
        let monitor = NWPathMonitor()
        monitor.pathUpdateHandler = { [weak self] path in
            let reachable = path.status == .satisfied
            let constrained = path.isExpensive || path.isConstrained || path.usesInterfaceType(.cellular)
            Task { @MainActor in
                guard let self else { return }
                let becameReachable = reachable && !self.isNetworkReachable
                self.isNetworkReachable = reachable
                self.isConstrainedNetwork = constrained
                if becameReachable, self.isAwaitingReconnectToResume {
                    self.isAwaitingReconnectToResume = false
                    await self.resumePlaybackAfterReconnect()
                }
            }
        }
        monitor.start(queue: DispatchQueue(label: "com.mekamb.music.network-monitor"))
        pathMonitor = monitor
    }

    /// Called when the currently playing item stalls or fails — most likely a network drop.
    /// If the background cache for this track has already finished, swap to it seamlessly at the
    /// current position; otherwise wait for connectivity to return and reload the same stream
    /// from where it left off. A track that drops in its first few seconds (before the background
    /// cache can finish) may still hiccup once — there's no way to have a local copy of audio
    /// that hasn't been downloaded yet — but playback recovers on its own as soon as either the
    /// cache finishes or the network returns, instead of staying silently stuck.
    private func handlePlaybackInterruption(for track: ApiTrack) async {
        guard currentTrack?.id == track.id, !isRecoveringPlayback else { return }
        if let cachedURL = localPlaybackCacheFileURL(for: track) {
            isRecoveringPlayback = true
            defer { isRecoveringPlayback = false }
            swapToLocalFile(cachedURL, for: track)
        } else {
            isAwaitingReconnectToResume = true
        }
    }

    private func resumePlaybackAfterReconnect() async {
        guard let track = currentTrack, !isRecoveringPlayback else { return }
        isRecoveringPlayback = true
        defer { isRecoveringPlayback = false }
        if let cachedURL = localPlaybackCacheFileURL(for: track) {
            swapToLocalFile(cachedURL, for: track)
        } else {
            let resumeElapsed = player?.currentTime().seconds ?? currentElapsedTime()
            play(track, updateQueue: false, startAt: resumeElapsed)
        }
    }

    /// Swaps the live AVPlayerItem for one backed by a local file, preserving playback position,
    /// without going through `play()` (which would re-resolve the source and could re-trigger a
    /// remote download attempt).
    private func swapToLocalFile(_ fileURL: URL, for track: ApiTrack) {
        let resumeElapsed = player?.currentTime().seconds ?? currentElapsedTime()
        removePlaybackItemObservers()
        let item = AVPlayerItem(asset: AVURLAsset(url: fileURL))
        addPlaybackItemObservers(to: item, track: track)
        player?.replaceCurrentItem(with: item)
        if resumeElapsed > 0 {
            player?.seek(to: CMTime(seconds: resumeElapsed, preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero)
        }
        player?.play()
        isPlaying = true
        updateNowPlayingPlaybackRate(elapsed: resumeElapsed)
    }

    private func postPlaybackState() async {
        guard canUseApi else { return }
        let queueIds = queueTracks.map(\.id)
        let repeatValue: String
        switch repeatMode {
        case .off:
            repeatValue = "off"
        case .all:
            repeatValue = "queue"
        case .one:
            repeatValue = "track"
        }
        let payload: [String: Any] = [
            "current_track_id": (currentTrack?.id as Any?) ?? NSNull(),
            "position_seconds": currentElapsedTime(),
            "is_playing": isPlaying,
            "repeat_mode": repeatValue,
            "shuffle": shuffleEnabled,
            "active_device_id": UIDevice.current.identifierForVendor?.uuidString ?? "ios",
            "active_device_name": UIDevice.current.name,
            "queue_track_ids": queueIds
        ]
        guard JSONSerialization.isValidJSONObject(payload),
              let body = try? JSONSerialization.data(withJSONObject: payload) else { return }
        do {
            let _: EmptyResponse = try await request("/playback/state", method: "PUT", body: body)
        } catch {
            if !isCancellation(error) {
                // Playback continues locally; this only powers server-side queue prefetch.
            }
        }
    }

    private func schedulePlaybackPrefetch() {
        playbackPrefetchTask?.cancel()
        playbackPrefetchTask = Task { [weak self] in
            guard let self else { return }
            await self.prefetchUpcomingPlaybackTracks()
        }
    }

    /// Caches the next few queued tracks to disk so advancing the queue is a seamless local-file
    /// swap instead of waiting on a fresh stream. Extended from 1 to 2 tracks ahead so a quick
    /// skip still lands on an already-cached file.
    private func prefetchUpcomingPlaybackTracks() async {
        guard prefetchQueuedTracksEnabled else { return }
        let candidates = Array(upcomingQueueTracks.prefix(2))
        guard !candidates.isEmpty else { return }
        await withTaskGroup(of: Void.self) { group in
            for track in candidates {
                group.addTask { [weak self] in
                    await self?.cacheTrackToPlaybackDisk(track)
                }
            }
        }
    }

    /// Downloads a track to the playback cache directory if it isn't already available locally.
    /// Shared by the upcoming-queue prefetch above and the current-track background cache used
    /// for seamless offline fallback.
    private func cacheTrackToPlaybackDisk(_ track: ApiTrack) async {
        guard !isTrackAvailableOffline(track), localPlaybackCacheFileURL(for: track) == nil else { return }
        guard canUseApi, !playbackPrefetchingTrackIds.contains(track.id) else { return }
        playbackPrefetchingTrackIds.insert(track.id)
        defer { playbackPrefetchingTrackIds.remove(track.id) }

        let encodedId = encodePathComponent(track.id)
        let query = streamFormatParam(for: track) == "aac" ? "?format=aac" : ""
        guard let url = endpointURL(path: "/tracks/\(encodedId)/stream\(query)") else { return }
        do {
            var request = URLRequest(url: url)
            request.timeoutInterval = 120
            request.setValue("Bearer \(apiToken)", forHTTPHeaderField: "Authorization")
            let (temporaryURL, response) = try await URLSession.shared.download(for: request)
            guard !Task.isCancelled else {
                try? FileManager.default.removeItem(at: temporaryURL)
                return
            }
            guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
                try? FileManager.default.removeItem(at: temporaryURL)
                return
            }
            let targetURL = try playbackCacheFileURL(for: track)
            try? FileManager.default.removeItem(at: targetURL)
            try FileManager.default.moveItem(at: temporaryURL, to: targetURL)
        } catch {
            if !isCancellation(error) {
                if let cacheURL = try? playbackCacheFileURL(for: track) {
                    try? FileManager.default.removeItem(at: cacheURL)
                }
            }
        }
    }

    private func loadArtwork(trackId: String) async throws -> (image: UIImage, jpegData: Data)? {
        let encodedId = encodePathComponent(trackId)
        guard let url = endpointURL(path: "/tracks/\(encodedId)/artwork") else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        request.timeoutInterval = 20
        request.setValue("Bearer \(apiToken)", forHTTPHeaderField: "Authorization")
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else { return nil }
        guard let image = downsampleArtwork(data: data, maxPixelSize: 420),
              let jpegData = image.jpegData(compressionQuality: 0.85) else { return nil }
        return (image, jpegData)
    }

    /// Reads a previously-cached album cover straight from disk (fast local decode, no network).
    private func loadCachedArtworkFromDisk(albumId: String) -> UIImage? {
        guard let url = try? artworkCacheFileURL(albumId: albumId),
              let data = try? Data(contentsOf: url) else { return nil }
        return UIImage(data: data)
    }

    /// Fire-and-forget disk write so the next launch is a cache hit instead of a network fetch.
    private func persistArtworkToDisk(_ jpegData: Data, albumId: String) {
        Task.detached(priority: .utility) {
            guard let url = try? await self.artworkCacheFileURL(albumId: albumId) else { return }
            try? jpegData.write(to: url, options: .atomic)
        }
    }

    private func artworkCacheFileURL(albumId: String) throws -> URL {
        try artworkCacheDirectory().appendingPathComponent("\(safeFileComponent(albumId)).jpg", isDirectory: false)
    }

    private func artworkCacheDirectory() throws -> URL {
        let base = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("MekambMusic", isDirectory: true)
            .appendingPathComponent("ArtworkCache", isDirectory: true)
        try FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        return base
    }

    private func downsampleArtwork(data: Data, maxPixelSize: CGFloat) -> UIImage? {
        let options = [kCGImageSourceShouldCache: false] as CFDictionary
        guard let source = CGImageSourceCreateWithData(data as CFData, options) else { return nil }
        let downsampleOptions = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceShouldCacheImmediately: true,
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceThumbnailMaxPixelSize: maxPixelSize
        ] as CFDictionary
        guard let image = CGImageSourceCreateThumbnailAtIndex(source, 0, downsampleOptions) else { return nil }
        return UIImage(cgImage: image)
    }

    func indexerImportBody(for torrent: TorrentResult) throws -> Data {
        guard let infoHash = torrent.infoHash, !infoHash.isEmpty,
              let magnetLink = torrent.magnetLink, !magnetLink.isEmpty else {
            throw BackendError.message("Indexer result is missing a download link.")
        }
        let payload = IndexerImportPayload(
            name: torrent.name,
            torrentId: torrent.torrentId,
            infoHash: infoHash,
            magnetLink: magnetLink,
            uploader: torrent.uploader,
            sourceUrl: torrent.sourceUrl
        )
        return try JSONEncoder().encode(payload)
    }

    private func request<T: Decodable>(
        _ path: String,
        method: String = "GET",
        body: Data? = nil,
        extraHeaders: [String: String] = [:],
        requiresAuth: Bool = true
    ) async throws -> T {
        guard let url = endpointURL(path: path) else {
            throw BackendError.message("Bad API endpoint. Use http://IP:8000, for example http://192.168.1.50:8000.")
        }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 20
        request.httpBody = body
        if body != nil {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        if requiresAuth {
            request.setValue("Bearer \(apiToken)", forHTTPHeaderField: "Authorization")
        }
        for (name, value) in extraHeaders {
            request.setValue(value, forHTTPHeaderField: name)
        }
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw URLError(.badServerResponse) }
        guard (200..<300).contains(http.statusCode) else {
            // Auth errors (e.g. invalid_credentials, account_pending) use a structured
            // {code, message} detail; everything else is a plain string detail.
            if let structured = try? JSONDecoder().decode(ApiStructuredError.self, from: data),
               let message = structured.detail.message {
                throw BackendError.api(status: http.statusCode, message: message)
            }
            if let payload = try? JSONDecoder().decode(ApiError.self, from: data) {
                throw BackendError.api(status: http.statusCode, message: payload.detail)
            }
            throw BackendError.api(status: http.statusCode, message: "API error \(http.statusCode)")
        }
        if T.self == EmptyResponse.self { return EmptyResponse() as! T }
        return try JSONDecoder().decode(T.self, from: data)
    }

    private func endpointURL(path: String) -> URL? {
        let base = normalizedEndpoint.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard !base.isEmpty else { return nil }
        return URL(string: base + path)
    }

    private func normalizeEndpoint(_ value: String) -> String {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines).trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard !trimmed.isEmpty else { return "" }
        if trimmed.hasPrefix("http://") || trimmed.hasPrefix("https://") { return trimmed }
        return "http://\(trimmed)"
    }

    private func encodePathComponent(_ value: String) -> String {
        value.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? value
    }

    private func downloadFilename(for track: ApiTrack) -> String {
        let source = track.originalFilename?.isEmpty == false
            ? track.originalFilename!
            : "\(track.displayArtist) - \(track.title)"
        var cleaned = source.replacingOccurrences(
            of: #"[\\/:*?"<>|]+"#,
            with: "_",
            options: .regularExpression
        )
        cleaned = cleaned.trimmingCharacters(in: .whitespacesAndNewlines)
        if cleaned.isEmpty { cleaned = "track" }
        if cleaned.range(of: #"\.[A-Za-z0-9]{2,5}$"#, options: .regularExpression) != nil {
            return cleaned
        }
        let extensionName: String
        switch track.mediaType ?? "" {
        case let mediaType where mediaType.contains("flac"):
            extensionName = "flac"
        case let mediaType where mediaType.contains("mpeg"):
            extensionName = "mp3"
        case let mediaType where mediaType.contains("mp4"):
            extensionName = "m4a"
        default:
            extensionName = "audio"
        }
        return "\(cleaned).\(extensionName)"
    }

    private func isCancellation(_ error: Error) -> Bool {
        if error is CancellationError { return true }
        if let urlError = error as? URLError, urlError.code == .cancelled { return true }
        let text = error.localizedDescription.lowercased()
        return text == "cancelled" || text == "canceled"
    }

    private func isNotFound(_ error: Error) -> Bool {
        guard let backend = error as? BackendError else { return false }
        if case .api(let status, _) = backend { return status == 404 }
        return false
    }

    private func stableAlbumKey(for track: ApiTrack) -> String {
        albumGroupingKey(for: track)
    }

    private func albumGroupingKey(for track: ApiTrack) -> String {
        let artist = normalizedAlbumArtist(track.artist)
        let album = normalizedAlbumTitle(track.album)
            ?? normalizedAlbumTitle(albumCandidateFromFilename(track.originalFilename))
            ?? normalizedAlbumTitle(track.title)
            ?? track.id.lowercased()
        return "album|\(artist)|\(album)"
    }

    private func albumKeysMatch(_ left: String, _ right: String) -> Bool {
        if left == right { return true }
        let leftParts = left.split(separator: "|", omittingEmptySubsequences: false).map(String.init)
        let rightParts = right.split(separator: "|", omittingEmptySubsequences: false).map(String.init)
        guard leftParts.count >= 3, rightParts.count >= 3, leftParts[1] == rightParts[1] else { return false }
        let leftAlbum = leftParts[2]
        let rightAlbum = rightParts[2]
        guard min(leftAlbum.count, rightAlbum.count) >= 8 else { return false }
        return leftAlbum.hasPrefix(rightAlbum) || rightAlbum.hasPrefix(leftAlbum)
    }

    private func normalizedAlbumArtist(_ value: String?) -> String {
        guard let value = cleanDisplayValue(value) else { return "unknown artist" }
        return normalizedGroupingValue(primaryAlbumArtist(value)) ?? "unknown artist"
    }

    private func primaryAlbumArtist(_ artist: String) -> String {
        artist
            .replacingOccurrences(of: "\\s+(feat\\.?|ft\\.?|featuring)\\s+.*$", with: "", options: [.regularExpression, .caseInsensitive])
            .components(separatedBy: CharacterSet(charactersIn: ",&/"))
            .first?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? artist
    }

    private func normalizedAlbumTitle(_ value: String?) -> String? {
        guard var value = cleanDisplayValue(value) else { return nil }
        value = value.replacingOccurrences(of: #"\.[A-Za-z0-9]{2,5}$"#, with: "", options: .regularExpression)
        value = value.replacingOccurrences(of: #"\([^)]*\)|\[[^]]*\]"#, with: " ", options: .regularExpression)
        value = value.replacingOccurrences(of: #"(?i)\b(deluxe|explicit|clean|remaster(?:ed)?|bonus|itunes|apple music|spotify|web|flac|mp3|m4a|320|lossless|album)\b"#, with: " ", options: .regularExpression)
        value = value.replacingOccurrences(of: #"(?i)\b(cd|disc)\s*\d+\b"#, with: " ", options: .regularExpression)
        value = value.replacingOccurrences(of: #"^[\d\s._-]+"#, with: "", options: .regularExpression)
        value = value.replacingOccurrences(of: #"[._-]+"#, with: " ", options: .regularExpression)
        value = value.replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
        value = value.trimmingCharacters(in: .whitespacesAndNewlines.union(CharacterSet(charactersIn: ".-_…")))
        return normalizedGroupingValue(value)
    }

    private func albumCandidateFromFilename(_ filename: String?) -> String? {
        guard var filename = cleanDisplayValue(filename) else { return nil }
        filename = filename.replacingOccurrences(of: #"\.[A-Za-z0-9]{2,5}$"#, with: "", options: .regularExpression)
        filename = filename.replacingOccurrences(of: #"^\s*\d{1,3}\s*[-._)]\s*"#, with: "", options: .regularExpression)
        let separators = [" - ", " – ", " — "]
        for separator in separators {
            let parts = filename.components(separatedBy: separator)
            if parts.count >= 3 { return parts[1] }
        }
        return filename
    }

    private func normalizedGroupingValue(_ value: String?) -> String? {
        guard let value else { return nil }
        let folded = value
            .folding(options: [.diacriticInsensitive, .caseInsensitive, .widthInsensitive], locale: .current)
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        return folded.isEmpty ? nil : folded
    }

    private func bestAlbumTitle(from tracks: [ApiTrack]) -> String {
        mostCommonDisplayValue(tracks.compactMap { cleanDisplayValue($0.album) }) ?? "Unknown Album"
    }

    private func bestAlbumArtist(from tracks: [ApiTrack]) -> String {
        mostCommonDisplayValue(tracks.compactMap { cleanDisplayValue($0.artist) }) ?? "Various Artists"
    }

    private func cleanDisplayValue(_ value: String?) -> String? {
        guard let value else { return nil }
        let cleaned = value
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return cleaned.isEmpty ? nil : cleaned
    }

    private func mostCommonDisplayValue(_ values: [String]) -> String? {
        let grouped = Dictionary(grouping: values, by: { normalizedGroupingValue($0) ?? $0.lowercased() })
        return grouped
            .map { _, group in (value: group.sorted(by: stableStringOrder).first ?? group[0], count: group.count) }
            .sorted { left, right in
                if left.count != right.count { return left.count > right.count }
                return stableStringOrder(left.value, right.value)
            }
            .first?.value
    }

    private func stableAlbumOrder(_ left: Album, _ right: Album) -> Bool {
        let titleOrder = left.title.localizedStandardCompare(right.title)
        if titleOrder != .orderedSame { return titleOrder == .orderedAscending }
        let artistOrder = left.artist.localizedStandardCompare(right.artist)
        if artistOrder != .orderedSame { return artistOrder == .orderedAscending }
        return left.id < right.id
    }

    private func playlistSummaryOrder(_ left: PlaylistSummary, _ right: PlaylistSummary) -> Bool {
        let nameOrder = left.name.localizedStandardCompare(right.name)
        if nameOrder != .orderedSame { return nameOrder == .orderedAscending }
        return left.id < right.id
    }

    private func playlistDetailOrder(_ left: PlaylistDetail, _ right: PlaylistDetail) -> Bool {
        let nameOrder = left.name.localizedStandardCompare(right.name)
        if nameOrder != .orderedSame { return nameOrder == .orderedAscending }
        return left.id < right.id
    }

    private func stableLibraryTrackOrder(_ left: ApiTrack, _ right: ApiTrack) -> Bool {
        let albumOrder = left.displayAlbum.localizedStandardCompare(right.displayAlbum)
        if albumOrder != .orderedSame { return albumOrder == .orderedAscending }
        return originalAlbumTrackOrder(left, right)
    }

    private func originalAlbumTrackOrder(_ left: ApiTrack, _ right: ApiTrack) -> Bool {
        let leftNumber = trackNumber(left)
        let rightNumber = trackNumber(right)
        if leftNumber != rightNumber { return leftNumber < rightNumber }

        let leftCreated = createdTimestamp(left)
        let rightCreated = createdTimestamp(right)
        if leftCreated != rightCreated { return leftCreated < rightCreated }

        let titleOrder = left.title.localizedStandardCompare(right.title)
        if titleOrder != .orderedSame { return titleOrder == .orderedAscending }
        return left.id < right.id
    }

    private func trackNumber(_ track: ApiTrack) -> Int {
        let filenamePatterns = [
            #"(?:^|[/\s_-])(\d{1,3})\s*[.)_-]"#,
            #"(?:^|[/\s_-])(\d{1,3})\s+"#,
            #"-(\d{1,3})\s*[.)_-]"#
        ]
        if let number = firstNumber(in: track.originalFilename, patterns: filenamePatterns) { return number }

        let titlePatterns = [#"^(\d{1,3})\s*[.)_-]"#, #"^(\d{1,3})\s+"#]
        if let number = firstNumber(in: track.title, patterns: titlePatterns) { return number }
        return Int.max
    }

    private func firstNumber(in value: String?, patterns: [String]) -> Int? {
        guard let value, !value.isEmpty else { return nil }
        let range = NSRange(value.startIndex..<value.endIndex, in: value)
        for pattern in patterns {
            guard let regex = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) else { continue }
            guard let match = regex.firstMatch(in: value, options: [], range: range), match.numberOfRanges > 1 else { continue }
            guard let numberRange = Range(match.range(at: 1), in: value), let number = Int(value[numberRange]), number > 0 else { continue }
            return number
        }
        return nil
    }

    /// Shared ISO-8601 parsers. Allocating an `ISO8601DateFormatter` is surprisingly expensive, and
    /// `createdTimestamp` runs inside `stableLibraryTrackOrder` — the comparator every library sort
    /// uses — so the old per-call allocation cost tens of thousands of formatter creations per
    /// rebuild (~seconds of the cold-start hang). Reuse one instance each; main-actor only.
    private static let iso8601Fractional: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()
    private static let iso8601Plain: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()
    /// Memoizes parsed timestamps by their raw string. A given `created_at` always maps to the same
    /// instant, so this never needs invalidation — it just collapses O(n log n) sort-comparator
    /// parses down to one parse per distinct string.
    private var parsedTimestampCache: [String: TimeInterval] = [:]

    private func parseTimestampString(_ value: String) -> TimeInterval? {
        if let cached = parsedTimestampCache[value] { return cached }
        let parsed = Self.iso8601Fractional.date(from: value)?.timeIntervalSince1970
            ?? Self.iso8601Plain.date(from: value)?.timeIntervalSince1970
        if let parsed { parsedTimestampCache[value] = parsed }
        return parsed
    }

    private func createdTimestamp(_ track: ApiTrack) -> TimeInterval {
        guard let createdAt = track.createdAt, !createdAt.isEmpty else { return 0 }
        return parseTimestampString(createdAt) ?? 0
    }

    private func stableStringOrder(_ left: String, _ right: String) -> Bool {
        let order = left.localizedStandardCompare(right)
        if order != .orderedSame { return order == .orderedAscending }
        return left < right
    }

    private func configureAudioSession() {
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playback, mode: .default, policy: .longFormAudio)
            try session.setActive(true)
        } catch {
            errorMessage = "Audio session error: \(error.localizedDescription)"
        }
    }

    private func configureRemoteCommandCenter() {
        let commandCenter = MPRemoteCommandCenter.shared()
        commandCenter.playCommand.isEnabled = true
        commandCenter.pauseCommand.isEnabled = true
        commandCenter.togglePlayPauseCommand.isEnabled = true
        commandCenter.nextTrackCommand.isEnabled = true
        commandCenter.previousTrackCommand.isEnabled = true
        commandCenter.changePlaybackPositionCommand.isEnabled = true

        commandCenter.playCommand.addTarget { [weak self] _ in
            Task { @MainActor in
                guard let self else { return }
                if !self.isPlaying { self.togglePlayback() }
            }
            return .success
        }

        commandCenter.pauseCommand.addTarget { [weak self] _ in
            Task { @MainActor in
                guard let self else { return }
                if self.isPlaying { self.togglePlayback() }
            }
            return .success
        }

        commandCenter.togglePlayPauseCommand.addTarget { [weak self] _ in
            Task { @MainActor in self?.togglePlayback() }
            return .success
        }

        commandCenter.nextTrackCommand.addTarget { [weak self] _ in
            Task { @MainActor in self?.nextTrack() }
            return .success
        }

        commandCenter.previousTrackCommand.addTarget { [weak self] _ in
            Task { @MainActor in self?.previousTrack() }
            return .success
        }

        commandCenter.changePlaybackPositionCommand.addTarget { [weak self] event in
            guard let event = event as? MPChangePlaybackPositionCommandEvent else { return .commandFailed }
            Task { @MainActor in self?.seek(to: event.positionTime) }
            return .success
        }
    }

    func seek(to seconds: TimeInterval) {
        let time = CMTime(seconds: seconds, preferredTimescale: 600)
        player?.seek(to: time)
        saveCurrentPlaybackPosition(elapsed: seconds)
        updateNowPlayingPlaybackRate(elapsed: seconds)
    }

    private func updateNowPlayingInfo(for track: ApiTrack, elapsed: TimeInterval) {
        var info: [String: Any] = [
            MPMediaItemPropertyTitle: track.title,
            MPMediaItemPropertyArtist: track.displayArtist,
            MPMediaItemPropertyAlbumTitle: track.displayAlbum,
            MPNowPlayingInfoPropertyElapsedPlaybackTime: elapsed,
            MPNowPlayingInfoPropertyPlaybackRate: isPlaying ? 1.0 : 0.0
        ]
        if let duration = track.durationSeconds, duration.isFinite, duration > 0 {
            info[MPMediaItemPropertyPlaybackDuration] = duration
        }
        if let image = nowPlayingArtworkImage(for: track) {
            info[MPMediaItemPropertyArtwork] = MPMediaItemArtwork(boundsSize: image.size) { _ in image }
        }
        MPNowPlayingInfoCenter.default().nowPlayingInfo = info
        fetchNowPlayingArtworkIfNeeded(for: track)
    }

    /// Best available cover for the lock screen without touching the network: the in-memory album
    /// cover if the home grid already loaded it, otherwise the on-disk artwork cache.
    private func nowPlayingArtworkImage(for track: ApiTrack) -> UIImage? {
        coverImage(for: track) ?? loadCachedArtworkFromDisk(albumId: stableAlbumKey(for: track))
    }

    /// When no cover is cached yet (e.g. playing a track before its album art loaded), fetch it
    /// once and splice it into the current Now Playing info so the lock screen fills in. Also
    /// seeds the shared cover cache so the in-app UI benefits from the same fetch.
    private func fetchNowPlayingArtworkIfNeeded(for track: ApiTrack) {
        guard nowPlayingArtworkImage(for: track) == nil, canUseApi else { return }
        let albumKey = stableAlbumKey(for: track)
        Task { [weak self] in
            guard let self else { return }
            guard let fetched = try? await self.loadArtwork(trackId: track.id) else { return }
            guard self.currentTrack?.id == track.id else { return }
            self.albumCovers[albumKey] = fetched.image
            self.persistArtworkToDisk(fetched.jpegData, albumId: albumKey)
            guard var info = MPNowPlayingInfoCenter.default().nowPlayingInfo else { return }
            info[MPMediaItemPropertyArtwork] = MPMediaItemArtwork(boundsSize: fetched.image.size) { _ in fetched.image }
            MPNowPlayingInfoCenter.default().nowPlayingInfo = info
        }
    }

    private func updateNowPlayingPlaybackRate(elapsed: TimeInterval? = nil) {
        guard var info = MPNowPlayingInfoCenter.default().nowPlayingInfo else {
            if let currentTrack {
                updateNowPlayingInfo(for: currentTrack, elapsed: elapsed ?? currentElapsedTime())
            }
            return
        }
        info[MPNowPlayingInfoPropertyPlaybackRate] = isPlaying ? 1.0 : 0.0
        info[MPNowPlayingInfoPropertyElapsedPlaybackTime] = elapsed ?? currentElapsedTime()
        MPNowPlayingInfoCenter.default().nowPlayingInfo = info
    }

    private func currentElapsedTime() -> TimeInterval {
        guard let seconds = player?.currentTime().seconds, seconds.isFinite else { return 0 }
        return seconds
    }

    private func addTimeObserver(to observedPlayer: AVPlayer) {
        removeTimeObserver()
        let interval = CMTime(seconds: 1, preferredTimescale: 600)
        timeObserver = observedPlayer.addPeriodicTimeObserver(forInterval: interval, queue: .main) { [weak self, weak observedPlayer] time in
            Task { @MainActor [weak self, weak observedPlayer] in
                guard let self else { return }
                let duration = observedPlayer?.currentItem?.duration.seconds ?? 0
                if duration.isFinite, duration > 0 {
                    self.playbackProgress = min(max(time.seconds / duration, 0), 1)
                }
                if var session = self.playSession, session.track.id == self.currentTrack?.id, time.seconds.isFinite {
                    session.maxElapsed = max(session.maxElapsed, time.seconds)
                    self.playSession = session
                }
                self.saveCurrentPlaybackPosition(elapsed: time.seconds)
                self.updateNowPlayingPlaybackRate(elapsed: time.seconds)
            }
        }
        timeObserverPlayer = observedPlayer
    }

    private func removeTimeObserver() {
        if let timeObserver, let timeObserverPlayer {
            timeObserverPlayer.removeTimeObserver(timeObserver)
        }
        timeObserver = nil
        timeObserverPlayer = nil
    }

    /// Mirrors the player's real transport state into `isPlaying`. Anything that pauses or resumes
    /// the player outside our own controls — the lock-screen/Control-Center buttons, Siri, a phone
    /// call or another app grabbing the audio session — flips `timeControlStatus`, and this keeps
    /// the in-app play/pause button and Now Playing rate honest instead of stuck on "playing".
    private func observePlayerState(_ observedPlayer: AVPlayer) {
        timeControlObserver = observedPlayer.observe(\.timeControlStatus, options: [.new]) { [weak self] player, _ in
            let playing = player.timeControlStatus != .paused
            Task { @MainActor [weak self] in
                guard let self, self.player === player else { return }
                guard self.isPlaying != playing else { return }
                self.isPlaying = playing
                self.updateNowPlayingPlaybackRate()
            }
        }
    }

    private func removePlayerStateObserver() {
        timeControlObserver?.invalidate()
        timeControlObserver = nil
    }

    private func removePlayerItemEndObserver() {
        if let playerItemEndObserver {
            NotificationCenter.default.removeObserver(playerItemEndObserver)
        }
        playerItemEndObserver = nil
    }

    private func clean(_ error: Error) -> String {
        if let backend = error as? BackendError { return backend.localizedDescription }
        if let urlError = error as? URLError {
            switch urlError.code {
            case .cannotConnectToHost, .notConnectedToInternet, .timedOut, .networkConnectionLost:
                return "Cannot reach backend at \(normalizedEndpoint). Make sure the backend is running, the iPhone is on the same Wi‑Fi, and you used the LAN IP, not localhost."
            default:
                return urlError.localizedDescription
            }
        }
        return error.localizedDescription
    }
}

struct EmptyResponse: Decodable {}

struct ApiError: Decodable { let detail: String }

struct ApiStructuredError: Decodable {
    struct Detail: Decodable {
        let code: String?
        let message: String?
    }
    let detail: Detail
}

// MARK: - Account auth payloads

struct AuthUserPayload: Decodable, Identifiable {
    let id: String
    let email: String
    let username: String
    let status: String
    let isAdmin: Bool

    enum CodingKeys: String, CodingKey {
        case id, email, username, status
        case isAdmin = "is_admin"
    }
}

struct AuthSessionPayload: Decodable {
    let token: String
    let user: AuthUserPayload
}

struct AuthRegisterPayload: Decodable {
    let user: AuthUserPayload
    let token: String?
    let message: String
}

struct LoginPayload: Encodable {
    let identifier: String
    let password: String
    let deviceName: String

    enum CodingKeys: String, CodingKey {
        case identifier, password
        case deviceName = "device_name"
    }
}

struct RegisterPayload: Encodable {
    let email: String
    let username: String
    let password: String
}

struct AdminUserListPayload: Decodable {
    let users: [AuthUserPayload]
}

enum BackendError: LocalizedError {
    case api(status: Int, message: String)
    case message(String)

    var errorDescription: String? {
        switch self {
        case .api(let status, let message):
            return "\(status): \(message)"
        case .message(let value):
            return value
        }
    }
}
