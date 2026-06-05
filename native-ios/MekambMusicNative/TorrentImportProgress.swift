import Foundation
import SwiftUI

struct TorrentImportProgressState: Equatable {
    let importId: String?
    let status: String
    let progress: Double
    let details: String

    var clampedProgress: Double {
        min(max(progress, 0), 1)
    }

    var percentText: String {
        "\(Int((clampedProgress * 100).rounded()))%"
    }

    var isTerminal: Bool {
        ["imported", "failed", "canceled", "cancelled"].contains(normalizedStatus)
    }

    var isFailure: Bool {
        ["failed"].contains(normalizedStatus)
    }

    var normalizedStatus: String {
        status.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

private struct NativeImportRecord: Decodable {
    let id: String
    let status: String
    let torrentId: String?
    let errorMessage: String?
    let sourceUrl: String?

    enum CodingKeys: String, CodingKey {
        case id
        case status
        case torrentId = "torrent_id"
        case errorMessage = "error_message"
        case sourceUrl = "source_url"
    }
}

private struct NativeTorrentDownload: Decodable {
    let progress: Double?
    let downloadedBytes: Int?
    let sizeBytes: Int?
    let downloadSpeedBytes: Int?
    let etaSeconds: Double?
    let state: String?

    enum CodingKeys: String, CodingKey {
        case progress
        case downloadedBytes = "downloaded_bytes"
        case sizeBytes = "size_bytes"
        case downloadSpeedBytes = "download_speed_bytes"
        case etaSeconds = "eta_seconds"
        case state
    }
}

private struct NativeDownloadPayload: Decodable {
    let importRecord: NativeImportRecord?
    let torrent: NativeTorrentDownload?

    enum CodingKeys: String, CodingKey {
        case importRecord = "import"
        case torrent
    }
}

@MainActor
final class TorrentImportController: ObservableObject {
    @Published var progress: TorrentImportProgressState?
    @Published var isRunning = false

    func start(torrent: TorrentResult, app: AppState) async {
        guard !isRunning else { return }
        isRunning = true
        app.errorMessage = nil
        progress = TorrentImportProgressState(importId: nil, status: "queued", progress: 0, details: "Adding to import queue…")

        do {
            let encodedId = encodePathComponent(torrent.torrentId)
            let record: NativeImportRecord = try await request(
                path: "\(torrent.source.importPath)/\(encodedId)",
                method: "POST",
                app: app
            )
            progress = progressState(importRecord: record, torrent: nil, fallbackTitle: torrent.name)
            await pollImport(record.id, torrentTitle: torrent.name, app: app)
        } catch {
            guard !isCancellation(error) else {
                progress = nil
                isRunning = false
                return
            }
            let message = clean(error, app: app)
            progress = TorrentImportProgressState(importId: nil, status: "failed", progress: 0, details: message)
            app.errorMessage = message
            isRunning = false
        }
    }

    private func pollImport(_ importId: String, torrentTitle: String, app: AppState) async {
        var sawImported = false

        for _ in 0..<900 {
            do {
                let encodedId = encodePathComponent(importId)
                let payload: NativeDownloadPayload = try await request(path: "/downloads/\(encodedId)", app: app)
                let nextProgress = progressState(
                    importRecord: payload.importRecord,
                    torrent: payload.torrent,
                    fallbackTitle: torrentTitle
                )
                progress = nextProgress

                if nextProgress.normalizedStatus == "imported" {
                    sawImported = true
                    await app.refreshLibrary()
                    progress = TorrentImportProgressState(
                        importId: importId,
                        status: "imported",
                        progress: 1,
                        details: "Imported successfully"
                    )
                    try? await Task.sleep(nanoseconds: 2_000_000_000)
                    progress = nil
                    isRunning = false
                    return
                }

                if ["canceled", "cancelled"].contains(nextProgress.normalizedStatus) {
                    if sawImported {
                        progress = nil
                    } else {
                        progress = TorrentImportProgressState(
                            importId: importId,
                            status: "stopped",
                            progress: nextProgress.clampedProgress,
                            details: "Import stopped"
                        )
                    }
                    isRunning = false
                    return
                }

                if nextProgress.isTerminal {
                    isRunning = false
                    return
                }
            } catch {
                if isCancellation(error) {
                    isRunning = false
                    return
                }
                progress = TorrentImportProgressState(
                    importId: importId,
                    status: "downloading",
                    progress: progress?.clampedProgress ?? 0,
                    details: "Waiting for backend status…"
                )
            }

            try? await Task.sleep(nanoseconds: 1_250_000_000)
        }

        isRunning = false
    }

    private func progressState(importRecord: NativeImportRecord?, torrent: NativeTorrentDownload?, fallbackTitle: String) -> TorrentImportProgressState {
        let status = importRecord?.status ?? "downloading"
        let torrentProgress = torrent?.progress ?? statusProgressFallback(status)
        let details: String

        if let torrent {
            let downloaded = formatBytes(torrent.downloadedBytes ?? 0)
            let total = formatBytes(torrent.sizeBytes ?? 0)
            let speed = formatBytes(torrent.downloadSpeedBytes ?? 0)
            let eta = formatDuration(torrent.etaSeconds ?? 0)
            let state = torrent.state ?? status
            details = "\(downloaded) / \(total) · \(speed)/s · ETA \(eta) · \(state)"
        } else if let error = importRecord?.errorMessage, !error.isEmpty {
            details = error
        } else {
            details = fallbackTitle
        }

        return TorrentImportProgressState(
            importId: importRecord?.id,
            status: status,
            progress: torrentProgress,
            details: details
        )
    }

    private func statusProgressFallback(_ status: String) -> Double {
        switch status.lowercased() {
        case "queued": return 0.03
        case "downloading": return 0.12
        case "ready_to_import": return 0.92
        case "importing": return 0.96
        case "imported": return 1
        default: return 0
        }
    }

    private func request<T: Decodable>(path: String, method: String = "GET", app: AppState) async throws -> T {
        guard let url = endpointURL(path: path, app: app) else {
            throw BackendError.message("Bad API endpoint. Use http://IP:8000.")
        }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 20
        request.setValue("Bearer \(app.apiToken)", forHTTPHeaderField: "Authorization")

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw URLError(.badServerResponse) }
        guard (200..<300).contains(http.statusCode) else {
            if let payload = try? JSONDecoder().decode(ApiError.self, from: data) {
                throw BackendError.message("\(http.statusCode): \(payload.detail)")
            }
            throw BackendError.message("API error \(http.statusCode)")
        }
        return try JSONDecoder().decode(T.self, from: data)
    }

    private func endpointURL(path: String, app: AppState) -> URL? {
        let base = app.normalizedEndpoint.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard !base.isEmpty else { return nil }
        return URL(string: base + path)
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

    private func formatBytes(_ bytes: Int) -> String {
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

    private func formatDuration(_ seconds: Double) -> String {
        guard seconds.isFinite, seconds > 0, seconds < 8_640_000 else { return "unknown" }
        if seconds >= 3600 {
            let hours = Int(seconds) / 3600
            let minutes = (Int(seconds) % 3600) / 60
            return "\(hours)h \(minutes)m"
        }
        let minutes = Int(seconds) / 60
        let rest = Int(seconds) % 60
        return "\(minutes):\(String(format: "%02d", rest))"
    }

    private func clean(_ error: Error, app: AppState) -> String {
        if let backend = error as? BackendError { return backend.localizedDescription }
        if let urlError = error as? URLError {
            switch urlError.code {
            case .cannotConnectToHost, .notConnectedToInternet, .timedOut, .networkConnectionLost:
                return "Cannot reach backend at \(app.normalizedEndpoint)."
            default:
                return urlError.localizedDescription
            }
        }
        return error.localizedDescription
    }
}
