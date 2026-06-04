import AVFoundation
import Foundation
import SwiftUI

struct ApiTrack: Identifiable, Codable, Hashable {
    let id: String
    let title: String
    let artist: String?
    let album: String?
    let originalFilename: String?
    let mediaType: String?
    let durationSeconds: Double?
    let sizeBytes: Int?

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case artist
        case album
        case originalFilename = "original_filename"
        case mediaType = "media_type"
        case durationSeconds = "duration_seconds"
        case sizeBytes = "size_bytes"
    }

    var displayArtist: String { artist?.isEmpty == false ? artist! : "Unknown Artist" }
    var displayAlbum: String { album?.isEmpty == false ? album! : "Unknown Album" }
    var durationText: String {
        guard let durationSeconds, durationSeconds.isFinite, durationSeconds > 0 else { return "0:00" }
        let total = Int(durationSeconds.rounded())
        return "\(total / 60):\(String(format: "%02d", total % 60))"
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
    case liked = "Liked"
    case settings = "Settings"
    var id: String { rawValue }
}

@MainActor
final class AppState: ObservableObject {
    @AppStorage("mekambMusicApiEndpoint") var apiEndpoint: String = "http://localhost:8000"
    @AppStorage("mekambMusicApiToken") var apiToken: String = ""

    @Published var searchMode: SearchMode = .library
    @Published var selectedTab: MusicTab = .library
    @Published var searchText: String = ""
    @Published var tracks: [ApiTrack] = []
    @Published var likedTrackIds: Set<String> = []
    @Published var torrents: [TorrentResult] = []
    @Published var isLoading = false
    @Published var isSearchingTorrents = false
    @Published var errorMessage: String?
    @Published var currentTrack: ApiTrack?
    @Published var isPlaying = false
    @Published var playbackProgress: Double = 0

    private var player: AVPlayer?
    private var timeObserver: Any?

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

    var canUseApi: Bool {
        !apiEndpoint.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        && !apiToken.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    func refreshLibrary() async {
        guard canUseApi else {
            errorMessage = "Set API endpoint and token in Settings."
            return
        }
        isLoading = true
        errorMessage = nil
        do {
            async let likedResponse: LikedTracksResponse = request("/tracks/liked?limit=200")
            async let trackResponse: TrackListResponse = request("/tracks?limit=200")
            let (liked, allTracks) = try await (likedResponse, trackResponse)
            likedTrackIds = Set(liked.items.map { $0.track.id })
            tracks = allTracks.items
            if currentTrack == nil { currentTrack = tracks.first }
        } catch {
            errorMessage = clean(error)
        }
        isLoading = false
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
        let encodedId = encodePathComponent(track.id)
        guard let url = endpointURL(path: "/tracks/\(encodedId)/stream") else { return }
        let headers = ["Authorization": "Bearer \(apiToken)"]
        let asset = AVURLAsset(url: url, options: ["AVURLAssetHTTPHeaderFieldsKey": headers])
        let item = AVPlayerItem(asset: asset)
        player?.pause()
        player = AVPlayer(playerItem: item)
        addTimeObserver()
        player?.play()
        isPlaying = true
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
            player.play()
            isPlaying = true
        }
    }

    func nextTrack() {
        let list = filteredTracks.isEmpty ? tracks : filteredTracks
        guard let currentTrack, let index = list.firstIndex(where: { $0.id == currentTrack.id }), !list.isEmpty else {
            if let first = list.first { play(first) }
            return
        }
        play(list[(index + 1) % list.count])
    }

    func previousTrack() {
        let list = filteredTracks.isEmpty ? tracks : filteredTracks
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

    private func request<T: Decodable>(_ path: String, method: String = "GET") async throws -> T {
        guard let url = endpointURL(path: path) else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 20
        if path != "/health" {
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
        let base = apiEndpoint.trimmingCharacters(in: .whitespacesAndNewlines).trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        return URL(string: base + path)
    }

    private func encodePathComponent(_ value: String) -> String {
        value.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? value
    }

    private func addTimeObserver() {
        if let timeObserver { player?.removeTimeObserver(timeObserver) }
        let interval = CMTime(seconds: 0.5, preferredTimescale: 600)
        timeObserver = player?.addPeriodicTimeObserver(forInterval: interval, queue: .main) { [weak self] time in
            guard let self else { return }
            let duration = self.player?.currentItem?.duration.seconds ?? 0
            guard duration.isFinite, duration > 0 else { return }
            self.playbackProgress = min(max(time.seconds / duration, 0), 1)
        }
    }

    private func clean(_ error: Error) -> String {
        if let backend = error as? BackendError { return backend.localizedDescription }
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
