import AVFoundation
import Foundation
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

    var trackCountText: String {
        tracks.count == 1 ? "1 song" : "\(tracks.count) songs"
    }
}

struct TrackListResponse: Codable {
    let items: [ApiTrack]
}

struct LikedTrackItem: Codable {
    let track: ApiTrack
}

struct LikedTracksResponse: Codable {
    let items: [LikedTrackItem]
}

struct TorrentResult: Identifiable, Codable, Hashable {
    let name: String
    let torrentId: String
    let seeders: String?
    let leechers: String?
    let sizeBytes: Int?
    let uploader: String?

    enum CodingKeys: String, CodingKey {
        case name
        case torrentId = "torrent_id"
        case seeders
        case leechers
        case sizeBytes = "size_bytes"
        case uploader
    }

    var id: String { torrentId }
    var sizeText: String {
        guard let sizeBytes, sizeBytes > 0 else { return "0 B" }
        let units = ["B", "KB", "MB", "GB", "TB"]
        var value = Double(sizeBytes)
        var index = 0
        while value >= 1024, index < units.count - 1 {
            value /= 1024
            index += 1
        }
        return index == 0 ? "\(Int(value)) \(units[index])" : String(format: "%.1f %@", value, units[index])
    }
}

struct TorrentSearchResponse: Codable {
    let items: [TorrentResult]
}

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

@MainActor
final class AppState: ObservableObject {
    @AppStorage("mekambMusicApiEndpoint") var apiEndpoint: String = ""
    @AppStorage("mekambMusicApiToken") var apiToken: String = ""

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

    private var player: AVPlayer?
    private var timeObserver: Any?
    private var playerItemEndObserver: NSObjectProtocol?

    init() {
        configureAudioSession()
        configureRemoteCommandCenter()
    }

    deinit {
        if let timeObserver { player?.removeTimeObserver(timeObserver) }
        if let playerItemEndObserver { NotificationCenter.default.removeObserver(playerItemEndObserver) }
    }

    var normalizedEndpoint: String {
        normalizeEndpoint(apiEndpoint)
    }

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
        let grouped = Dictionary(grouping: tracks) { track in
            stableAlbumKey(for: track)
        }

        return grouped
            .map { key, albumTracks in
                let sortedTracks = albumTracks.sorted(by: originalAlbumTrackOrder)
                let first = sortedTracks.first
                let title = bestAlbumTitle(from: sortedTracks)
                let artist = bestAlbumArtist(from: sortedTracks)
                return Album(
                    id: key,
                    title: title,
                    artist: artist,
                    tracks: sortedTracks,
                    coverTrackId: sortedTracks.first?.id ?? first?.id
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

    func testConnection() async {
        isTestingConnection = true
        errorMessage = nil
        connectionStatus = nil
        do {
            let _: EmptyResponse = try await request("/health", requiresAuth: false)
            connectionStatus = "Connected to \(normalizedEndpoint)"
        } catch {
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
            async let likedResponse: LikedTracksResponse = request("/tracks/liked?limit=200")
            async let trackResponse: TrackListResponse = request("/tracks?limit=200")
            let (liked, allTracks) = try await (likedResponse, trackResponse)
            likedTrackIds = Set(liked.items.map { $0.track.id })
            tracks = allTracks.items.sorted(by: stableLibraryTrackOrder)
            if currentTrack == nil { currentTrack = tracks.first }
            selectedAlbumId = selectedAlbumId.flatMap { id in albums.contains(where: { $0.id == id }) ? id : nil }
            Task { await loadMissingAlbumCovers() }
        } catch {
            errorMessage = clean(error)
        }
        isLoading = false
    }

    func loadMissingAlbumCovers() async {
        let targets = albums.compactMap { album -> (String, String)? in
            guard albumCovers[album.id] == nil, let trackId = album.coverTrackId else { return nil }
            return (album.id, trackId)
        }
        for (albumId, trackId) in targets {
            if let image = try? await loadArtwork(trackId: trackId) {
                albumCovers[albumId] = image
            }
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
            let response: TorrentSearchResponse = try await request("/sources/piratebay/search?q=\(encoded)")
            torrents = response.items.sorted { Int($0.seeders ?? "0") ?? 0 > Int($1.seeders ?? "0") ?? 0 }
        } catch {
            errorMessage = clean(error)
            torrents = []
        }
        isSearchingTorrents = false
    }

    func importTorrent(_ torrent: TorrentResult) async {
        errorMessage = nil
        do {
            let encodedId = encodePathComponent(torrent.torrentId)
            let _: EmptyResponse = try await request("/imports/piratebay/\(encodedId)", method: "POST")
        } catch {
            errorMessage = clean(error)
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
            errorMessage = clean(error)
        }
    }

    func play(_ track: ApiTrack) {
        currentTrack = track
        playbackProgress = 0
        configureAudioSession()

        let encodedId = encodePathComponent(track.id)
        guard let url = endpointURL(path: "/tracks/\(encodedId)/stream") else { return }
        let headers = ["Authorization": "Bearer \(apiToken)"]
        let asset = AVURLAsset(url: url, options: ["AVURLAssetHTTPHeaderFieldsKey": headers])
        let item = AVPlayerItem(asset: asset)

        if let playerItemEndObserver { NotificationCenter.default.removeObserver(playerItemEndObserver) }
        playerItemEndObserver = NotificationCenter.default.addObserver(
            forName: .AVPlayerItemDidPlayToEndTime,
            object: item,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor in self?.nextTrack() }
        }

        player?.pause()
        player = AVPlayer(playerItem: item)
        addTimeObserver()
        player?.play()
        isPlaying = true
        updateNowPlayingInfo(for: track, elapsed: 0)
        Task { try? await postPlay(track) }
    }

    func togglePlayback() {
        guard let player else {
            if let currentTrack { play(currentTrack) }
            return
        }
        if isPlaying {
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
        let list = selectedTab == .albums ? (selectedAlbum?.tracks ?? tracks) : (filteredTracks.isEmpty ? tracks : filteredTracks)
        guard let currentTrack, let index = list.firstIndex(where: { $0.id == currentTrack.id }), !list.isEmpty else {
            if let first = list.first { play(first) }
            return
        }
        play(list[(index + 1) % list.count])
    }

    func previousTrack() {
        let list = selectedTab == .albums ? (selectedAlbum?.tracks ?? tracks) : (filteredTracks.isEmpty ? tracks : filteredTracks)
        guard let currentTrack, let index = list.firstIndex(where: { $0.id == currentTrack.id }), !list.isEmpty else {
            if let first = list.first { play(first) }
            return
        }
        play(list[(index - 1 + list.count) % list.count])
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
        return UIImage(data: data)
    }

    private func request<T: Decodable>(_ path: String, method: String = "GET", requiresAuth: Bool = true) async throws -> T {
        guard let url = endpointURL(path: path) else { throw BackendError.message("Bad API endpoint. Use http://IP:8000, for example http://192.168.1.50:8000.") }
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
                throw BackendError.message("\(http.statusCode): \(payload.detail)")
            }
            throw BackendError.message("API error \(http.statusCode)")
        }
        if T.self == EmptyResponse.self { return EmptyResponse() as! T }
        let decoder = JSONDecoder()
        return try decoder.decode(T.self, from: data)
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
        if let number = firstNumber(in: track.originalFilename, patterns: filenamePatterns) {
            return number
        }

        let titlePatterns = [
            #"^(\d{1,3})\s*[.)_-]"#,
            #"^(\d{1,3})\s+"#
        ]
        if let number = firstNumber(in: track.title, patterns: titlePatterns) {
            return number
        }

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
        player?.currentTime().seconds.isFinite == true ? player?.currentTime().seconds ?? 0 : 0
    }

    private func addTimeObserver() {
        if let timeObserver { player?.removeTimeObserver(timeObserver) }
        let interval = CMTime(seconds: 0.5, preferredTimescale: 600)
        timeObserver = player?.addPeriodicTimeObserver(forInterval: interval, queue: .main) { [weak self] time in
            guard let self else { return }
            let duration = self.player?.currentItem?.duration.seconds ?? 0
            if duration.isFinite, duration > 0 {
                self.playbackProgress = min(max(time.seconds / duration, 0), 1)
            }
            self.updateNowPlayingPlaybackRate(elapsed: time.seconds)
        }
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

struct ApiError: Decodable {
    let detail: String
}

enum BackendError: LocalizedError {
    case message(String)
    var errorDescription: String? {
        switch self {
        case .message(let value):
            return value
        }
    }
}
