import AVFoundation
import Foundation
import ImageIO
import MediaPlayer
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

struct Album: Identifiable, Hashable {
    let id: String
    let title: String
    let artist: String
    let tracks: [ApiTrack]
    let coverTrackId: String?

    var trackCountText: String { tracks.count == 1 ? "1 song" : "\(tracks.count) songs" }
}

struct TrackListResponse: Codable { let items: [ApiTrack] }
struct LikedTrackItem: Codable { let track: ApiTrack }
struct LikedTracksResponse: Codable { let items: [LikedTrackItem] }

enum TorrentSource: String, Codable, CaseIterable, Identifiable {
    case pirateBay = "piratebay"
    case thirteenThirtySevenX = "1337x"

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .pirateBay:
            return "Pirate Bay"
        case .thirteenThirtySevenX:
            return "1337x"
        }
    }

    var searchPath: String {
        switch self {
        case .pirateBay:
            return "/sources/piratebay/search"
        case .thirteenThirtySevenX:
            return "/sources/1337x/search"
        }
    }

    var importPath: String {
        switch self {
        case .pirateBay:
            return "/imports/piratebay"
        case .thirteenThirtySevenX:
            return "/imports/1337x"
        }
    }
}

struct TorrentResult: Identifiable, Codable, Hashable {
    let name: String
    let torrentId: String
    let source: TorrentSource
    let seeders: String?
    let leechers: String?
    let sizeBytes: Int?
    let sizeLabel: String?
    let uploader: String?

    enum CodingKeys: String, CodingKey {
        case name
        case torrentId = "torrent_id"
        case source
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
        seeders: String?,
        leechers: String?,
        sizeBytes: Int?,
        sizeLabel: String?,
        uploader: String?
    ) {
        self.name = name
        self.torrentId = torrentId
        self.source = source
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
            seeders: seeders,
            leechers: leechers,
            sizeBytes: sizeBytes,
            sizeLabel: sizeLabel,
            uploader: uploader
        )
    }
}

struct TorrentSearchResponse: Codable { let items: [TorrentResult] }

enum SearchMode: String, CaseIterable, Identifiable {
    case library = "Library"
    case torrent = "Torrent"
    var id: String { rawValue }
}

enum MusicTab: String, CaseIterable, Identifiable {
    case library = "Library"
    case albums = "Albums"
    case liked = "Liked"
    case settings = "Settings"
    var id: String { rawValue }
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

@MainActor
final class AppState: ObservableObject {
    @AppStorage("mekambMusicApiEndpoint") var apiEndpoint: String = ""
    @AppStorage("mekambMusicApiToken") var apiToken: String = ""
    @AppStorage("mekambMusicAutoplaySimilarEnabled") var autoplaySimilarEnabled: Bool = true
    @AppStorage("mekambMusicLastTrackId") private var savedPlaybackTrackId: String = ""
    @AppStorage("mekambMusicLastElapsedTime") private var savedPlaybackElapsedTime: Double = 0

    @Published var searchMode: SearchMode = .library
    @Published var selectedTab: MusicTab = .library
    @Published var searchText: String = ""
    @Published var tracks: [ApiTrack] = []
    @Published var likedTrackIds: Set<String> = []
    @Published var torrents: [TorrentResult] = []
    @Published var albumCovers: [String: UIImage] = [:]
    @Published var selectedAlbumId: String?
    @Published var isLoading = false
    @Published var isSearchingTorrents = false
    @Published var isTestingConnection = false
    @Published var connectionStatus: String?
    @Published var errorMessage: String?
    @Published var currentTrack: ApiTrack?
    @Published var isPlaying = false
    @Published var playbackProgress: Double = 0
    @Published var playbackQueue: [ApiTrack] = []
    @Published var shuffleEnabled = false
    @Published var repeatMode: RepeatMode = .off

    private var player: AVPlayer?
    private var timeObserver: Any?
    private weak var timeObserverPlayer: AVPlayer?
    private var playerItemEndObserver: NSObjectProtocol?
    private var isLoadingAlbumCovers = false
    private var failedAlbumCoverIds: Set<String> = []
    private var didRestorePlaybackState = false

    init() {
        configureAudioSession()
        configureRemoteCommandCenter()
    }

    deinit {
        if let timeObserver, let timeObserverPlayer {
            timeObserverPlayer.removeTimeObserver(timeObserver)
        }
        if let playerItemEndObserver {
            NotificationCenter.default.removeObserver(playerItemEndObserver)
        }
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

    var albums: [Album] {
        let grouped = Dictionary(grouping: tracks) { track in stableAlbumKey(for: track) }
        return grouped
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
        isTestingConnection = true
        errorMessage = nil
        connectionStatus = nil
        do {
            let _: EmptyResponse = try await request("/health", requiresAuth: false)
            connectionStatus = "Connected to \(normalizedEndpoint)"
        } catch {
            guard !isCancellation(error) else {
                isTestingConnection = false
                return
            }
            let message = clean(error)
            connectionStatus = "Connection failed: \(message)"
            errorMessage = message
        }
        isTestingConnection = false
    }

    func refreshLibrary() async {
        guard canUseApi else {
            errorMessage = endpointWarning ?? "Set API endpoint and token in Settings."
            return
        }
        isLoading = true
        errorMessage = nil
        do {
            async let likedIds = loadAllLikedTrackIds()
            async let allTracks = loadAllTracks()
            let (newLikedIds, newTracks) = try await (likedIds, allTracks)
            likedTrackIds = newLikedIds
            tracks = mergeTracks(existing: tracks, incoming: newTracks).sorted(by: stableLibraryTrackOrder)
            syncQueueWithLibrary()
            restorePlaybackStateIfNeeded()
            selectedAlbumId = selectedAlbumId.flatMap { id in albums.contains(where: { $0.id == id }) ? id : nil }
            Task { await loadMissingAlbumCovers() }
        } catch {
            if !isCancellation(error) { errorMessage = clean(error) }
        }
        isLoading = false
    }

    func loadMissingAlbumCovers() async {
        guard !isLoadingAlbumCovers else { return }
        isLoadingAlbumCovers = true
        defer { isLoadingAlbumCovers = false }

        let targets = albums.compactMap { album -> (String, String)? in
            guard albumCovers[album.id] == nil, !failedAlbumCoverIds.contains(album.id), let trackId = album.coverTrackId else { return nil }
            return (album.id, trackId)
        }
        for (albumId, trackId) in targets {
            if let image = try? await loadArtwork(trackId: trackId) {
                albumCovers[albumId] = image
            } else {
                failedAlbumCoverIds.insert(albumId)
            }
            await Task.yield()
        }
    }

    func searchTorrents() async {
        let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard canUseApi, !query.isEmpty else {
            torrents = []
            return
        }
        isSearchingTorrents = true
        errorMessage = nil
        do {
            let encoded = query.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? query
            let items: [TorrentResult]
            do {
                let response: TorrentSearchResponse = try await request("/sources/search?q=\(encoded)")
                items = response.items
            } catch {
                guard isNotFound(error) else { throw error }
                items = try await searchLegacyTorrentSources(encodedQuery: encoded)
            }
            torrents = items.sorted { left, right in
                Int(left.seeders ?? "0") ?? 0 > Int(right.seeders ?? "0") ?? 0
            }
        } catch {
            if !isCancellation(error) {
                errorMessage = clean(error)
                torrents = []
            }
        }
        isSearchingTorrents = false
    }

    func importTorrent(_ torrent: TorrentResult) async {
        errorMessage = nil
        do {
            let encodedId = encodePathComponent(torrent.torrentId)
            let _: EmptyResponse = try await request("\(torrent.source.importPath)/\(encodedId)", method: "POST")
        } catch {
            if !isCancellation(error) { errorMessage = clean(error) }
        }
    }

    func toggleLike(_ track: ApiTrack) async {
        let willLike = !likedTrackIds.contains(track.id)
        if willLike { likedTrackIds.insert(track.id) } else { likedTrackIds.remove(track.id) }
        do {
            let encodedId = encodePathComponent(track.id)
            let _: EmptyResponse = try await request("/tracks/\(encodedId)/like", method: willLike ? "PUT" : "DELETE")
        } catch {
            if willLike { likedTrackIds.remove(track.id) } else { likedTrackIds.insert(track.id) }
            if !isCancellation(error) { errorMessage = clean(error) }
        }
    }

    func play(_ track: ApiTrack, queue: [ApiTrack]? = nil, updateQueue: Bool = true, startAt startTime: TimeInterval? = nil) {
        if updateQueue {
            preparePlaybackQueue(for: track, from: queue ?? playbackContextTracks())
        }

        let encodedId = encodePathComponent(track.id)
        guard let url = endpointURL(path: "/tracks/\(encodedId)/stream") else { return }

        configureAudioSession()
        removePlayerItemEndObserver()
        removeTimeObserver()
        player?.pause()

        let headers = ["Authorization": "Bearer \(apiToken)"]
        let asset = AVURLAsset(url: url, options: ["AVURLAssetHTTPHeaderFieldsKey": headers])
        let item = AVPlayerItem(asset: asset)
        let nextPlayer = AVPlayer(playerItem: item)

        playerItemEndObserver = NotificationCenter.default.addObserver(
            forName: .AVPlayerItemDidPlayToEndTime,
            object: item,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor in self?.nextTrack() }
        }

        player = nextPlayer
        currentTrack = track
        savedPlaybackTrackId = track.id
        let elapsed = normalizedPlaybackStartTime(startTime, for: track)
        savedPlaybackElapsedTime = elapsed
        playbackProgress = playbackProgress(for: elapsed, in: track)
        addTimeObserver(to: nextPlayer)
        if elapsed > 0 {
            nextPlayer.seek(to: CMTime(seconds: elapsed, preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero)
        }
        nextPlayer.play()
        isPlaying = true
        updateNowPlayingInfo(for: track, elapsed: elapsed)
        Task { try? await postPlay(track) }
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
            let recommendations = autoplaySimilarEnabled ? autoplayRecommendations(after: currentTrack, excluding: list) : []
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
            return
        }
        preparePlaybackQueue(for: currentTrack, from: playbackQueue.isEmpty ? playbackContextTracks() : playbackQueue)
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
    }

    func addToQueue(_ track: ApiTrack) {
        if playbackQueue.isEmpty, let currentTrack {
            playbackQueue = [currentTrack]
        }
        guard !playbackQueue.contains(where: { $0.id == track.id }) else { return }
        playbackQueue.append(track)
    }

    func removeFromQueue(_ track: ApiTrack) {
        guard currentTrack?.id != track.id else { return }
        playbackQueue.removeAll { $0.id == track.id }
    }

    func clearQueue() {
        playbackQueue = currentTrack.map { [$0] } ?? []
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

    private func playbackContextTracks() -> [ApiTrack] {
        if selectedTab == .albums, let selectedAlbum { return selectedAlbum.tracks }
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

    private func postPlay(_ track: ApiTrack) async throws {
        let encodedId = encodePathComponent(track.id)
        let _: EmptyResponse = try await request("/tracks/\(encodedId)/plays", method: "POST")
    }

    private func loadArtwork(trackId: String) async throws -> UIImage? {
        let encodedId = encodePathComponent(trackId)
        guard let url = endpointURL(path: "/tracks/\(encodedId)/artwork") else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        request.timeoutInterval = 20
        request.setValue("Bearer \(apiToken)", forHTTPHeaderField: "Authorization")
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else { return nil }
        return downsampleArtwork(data: data, maxPixelSize: 420)
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

    private func request<T: Decodable>(_ path: String, method: String = "GET", requiresAuth: Bool = true) async throws -> T {
        guard let url = endpointURL(path: path) else {
            throw BackendError.message("Bad API endpoint. Use http://IP:8000, for example http://192.168.1.50:8000.")
        }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 20
        if requiresAuth {
            request.setValue("Bearer \(apiToken)", forHTTPHeaderField: "Authorization")
        }
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw URLError(.badServerResponse) }
        guard (200..<300).contains(http.statusCode) else {
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
        let normalizedAlbum = normalizedGroupingValue(track.album) ?? normalizedGroupingValue(track.originalFilename) ?? track.id
        return "album|\(normalizedAlbum)"
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

    private func createdTimestamp(_ track: ApiTrack) -> TimeInterval {
        guard let createdAt = track.createdAt, !createdAt.isEmpty else { return 0 }
        let fractionalFormatter = ISO8601DateFormatter()
        fractionalFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = fractionalFormatter.date(from: createdAt) { return date.timeIntervalSince1970 }

        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: createdAt)?.timeIntervalSince1970 ?? 0
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

    private func seek(to seconds: TimeInterval) {
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
        MPNowPlayingInfoCenter.default().nowPlayingInfo = info
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
