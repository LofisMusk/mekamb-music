import SwiftUI

// MARK: - Library View

struct LibraryView: View {
    @EnvironmentObject private var app: AppState

    var body: some View {
        List(app.tracks, id: \.id) { track in
            TrackRowNative(track: track)
                .environmentObject(app)
                .listRowInsets(EdgeInsets(top: 6, leading: 12, bottom: 6, trailing: 12))
                .listRowSeparator(.hidden)
                .listRowBackground(Color.clear)
        }
        .listStyle(.plain)
        .scrollContentBackground(.hidden)
        .background(Color.clear)
        .scrollBounceBehavior(.basedOnSize)
        .onAppear {
            // Preload artwork
            _ = app.tracks.prefix(20).map { app.coverImage(for: $0) != nil }
        }
    }
}

// MARK: - Albums View

struct AlbumsView: View {
    @EnvironmentObject private var app: AppState
    @State private var showAlbumDetail = false
    @State private var detailAlbum: Album? = nil

    var body: some View {
        ScrollView {
            LazyVGrid(columns: [
                GridItem(.adaptive(minimum: 140, maximum: 200), spacing: 16)
            ], spacing: 16) {
                ForEach(app.albums) { album in
                    AlbumRow(album: album)
                        .environmentObject(app)
                        .onTapGesture {
                            detailAlbum = album
                            showAlbumDetail = true
                        }
                }
            }
            .padding(12)
        }
        .background(Color.clear)
        .sheet(isPresented: $showAlbumDetail) {
            if let album = detailAlbum {
                AlbumDetailSheet(album: album)
            }
        }
    }
}

struct AlbumDetailSheet: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var app: AppState
    let album: Album

    var body: some View {
        VStack(spacing: 16) {
            HStack {
                if let artwork = app.albumCovers[album.id] {
                    Image(uiImage: artwork)
                        .resizable()
                        .scaledToFill()
                        .frame(width: 120, height: 120)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                } else {
                    Rectangle()
                        .fill(
                            LinearGradient(
                                colors: [.blue.opacity(0.7), .purple.opacity(0.55)],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                        .frame(width: 120, height: 120)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                        .overlay {
                            Image(systemName: "music.note")
                                .font(.title)
                                .foregroundStyle(.white.opacity(0.6))
                        }
                }

                VStack(alignment: .leading, spacing: 6) {
                    Text(album.title)
                        .font(.title2.weight(.bold))
                    Text(album.artist)
                        .font(.body)
                        .foregroundStyle(.secondary)
                    Text("\(album.trackCount) songs")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(.top, 8)

                Spacer()
            }

            Divider()

            ScrollView {
                LazyVStack(spacing: 0) {
                    ForEach(album.tracks) { track in
                        TrackRowNative(track: track)
                            .environmentObject(app)
                            .listRowInsets(EdgeInsets(top: 4, leading: 8, bottom: 4, trailing: 8))
                            .listRowSeparator(.hidden)
                            .listRowBackground(Color.clear)
                    }
                }
                .listStyle(.plain)
                .scrollContentBackground(.hidden)
            }

            Divider()

            HStack(spacing: 12) {
                Button {
                    if let t = album.tracks.first {
                        app.play(t, queue: album.tracks, updateQueue: true)
                    }
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "play.fill")
                        Text("Play All")
                    }
                    .font(.subheadline.weight(.semibold))
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .tint(.blue)

                Button {
                    app.playShuffle(album.tracks)
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "shuffle")
                        Text("Shuffle")
                    }
                    .font(.subheadline.weight(.semibold))
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
            }
            .padding(.top, 8)
        }
        .padding(16)
        .frame(minWidth: 480, minHeight: 400)
        .background(Color(nsColor: .windowBackgroundColor))
    }
}

// MARK: - Liked View

struct LikedView: View {
    @EnvironmentObject private var app: AppState

    var body: some View {
        if app.loadingLiked {
            ProgressView("Loading liked tracks...")
                .padding()
        } else if let error = app.likedTracksError {
            VStack(spacing: 8) {
                Image(systemName: "exclamationmark.triangle")
                    .font(.title)
                    .foregroundStyle(.red)
                Text(error)
                    .foregroundStyle(.secondary)
                Button("Retry") {
                    Task { await app.fetchLikedTracks() }
                }
                .buttonStyle(.borderedProminent)
            }
        } else if app.likedTracks.isEmpty {
            VStack(spacing: 12) {
                Image(systemName: "heart")
                    .font(.system(size: 48))
                    .foregroundStyle(.tertiary)
                Text("No liked tracks yet")
                    .font(.title3)
                    .foregroundStyle(.secondary)
                Text("Heart songs from your library to see them here")
                    .font(.subheadline)
                    .foregroundStyle(.tertiary)
            }
        } else {
            List(app.likedTracks, id: \.id) { track in
                TrackRowNative(track: track)
                    .environmentObject(app)
                    .listRowInsets(EdgeInsets(top: 6, leading: 12, bottom: 6, trailing: 12))
                    .listRowSeparator(.hidden)
                    .listRowBackground(Color.clear)
            }
            .listStyle(.plain)
            .scrollContentBackground(.hidden)
            .scrollBounceBehavior(.basedOnSize)
        }
    }
}

// MARK: - Torrent Search View

struct TorrentSearchView: View {
    @EnvironmentObject private var app: AppState

    var body: some View {
        ScrollView {
            LazyVStack(spacing: 10) {
                if app.torrents.isEmpty && !app.loadingTorrents {
                    VStack(spacing: 8) {
                        Image(systemName: "cloud")
                            .font(.title)
                            .foregroundStyle(.tertiary)
                        Text("Search torrents for your music")
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity)
                }

                ForEach(app.torrents) { torrent in
                    TorrentRow(torrent: torrent)
                }
            }
            .padding(12)
        }
        .background(Color.clear)
        .overlay {
            if app.loadingTorrents {
                ProgressView("Searching torrents...")
                    .padding(12)
            }
        }
    }
}

struct TorrentRow: View {
    @EnvironmentObject private var app: AppState
    @State private var showProgress = false

    let torrent: TorrentResult

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "cloud.fill")
                .font(.title3)
                .foregroundStyle(.secondary)
                .frame(width: 40)

            VStack(alignment: .leading, spacing: 3) {
                Text(torrent.name)
                    .font(.subheadline.weight(.medium))
                    .lineLimit(1)
                HStack(spacing: 6) {
                    Text(torrent.source.rawValue)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text("•")
                        .foregroundStyle(.tertiary)
                    Text("\(torrent.sizeStr)")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    if torrent.seeders >= 5 {
                        Image(systemName: "arrow.up.circle.fill")
                            .font(.caption2)
                            .foregroundStyle(.green)
                    }
                }
            }

            Spacer()

            if torrent.downloaded {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(.green)
            } else if app.downloadingTorrents.contains(torrent) {
                ProgressView()
                    .controlSize(.small)
            } else {
                Button {
                    showProgress = true
                } label: {
                    Image(systemName: "cloud.arrow.down")
                        .font(.body)
                        .foregroundStyle(.blue)
                        .frame(width: 28, height: 28)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(10)
        .background(Color(nsColor: .textBackgroundColor).opacity(0.4))
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
    }
}

// MARK: - Indexer Search View

struct IndexerSearchView: View {
    @EnvironmentObject private var app: AppState

    var body: some View {
        List(app.indexerResults, id: \.id) { result in
            HStack(spacing: 10) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.secondary)
                    .frame(width: 24)
                VStack(alignment: .leading, spacing: 2) {
                    Text(result.name)
                        .font(.subheadline)
                        .lineLimit(1)
                    Text(result.url)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                Spacer()
            }
            .padding(.vertical, 4)
        }
        .listStyle(.plain)
        .scrollContentBackground(.hidden)
    }
}

// MARK: - Queue View

struct QueueView: View {
    @EnvironmentObject private var app: AppState

    var body: some View {
        VStack(spacing: 12) {
            if let current = app.currentTrack {
                VStack(spacing: 8) {
                    TrackArtworkView(track: current, size: 120)
                        .environmentObject(app)
                    VStack(spacing: 4) {
                        Text(current.title)
                            .font(.headline)
                            .multilineTextAlignment(.center)
                        Text(current.displayArtist)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(.bottom, 8)

                Divider()
            }

            ScrollView {
                LazyVStack(spacing: 0) {
                    if let current = app.currentTrack {
                        Label("Now Playing", systemImage: "play.circle.fill")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .textCase(.uppercase)
                            .padding(.horizontal, 4)

                        QueueTrackRow(track: current, isCurrent: true)
                            .environmentObject(app)
                            .listRowInsets(EdgeInsets(top: 4, leading: 4, bottom: 4, trailing: 4))
                            .listRowSeparator(.hidden)
                            .listRowBackground(Color.clear)
                    }

                    if !app.upcomingQueueTracks.isEmpty {
                        Label("Up Next", systemImage: "forward.fill")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .textCase(.uppercase)
                            .padding(.horizontal, 4)
                            .padding(.top, 8)

                        ForEach(app.upcomingQueueTracks) { track in
                            QueueTrackRow(track: track, isCurrent: false)
                                .environmentObject(app)
                                .listRowInsets(EdgeInsets(top: 4, leading: 4, bottom: 4, trailing: 4))
                                .listRowSeparator(.hidden)
                                .listRowBackground(Color.clear)
                        }
                    }
                }
            }
            .scrollContentBackground(.hidden)
        }
        .padding(12)
    }
}

struct QueueTrackRow: View {
    @EnvironmentObject private var app: AppState
    let track: ApiTrack
    let isCurrent: Bool

    var body: some View {
        HStack(spacing: 10) {
            TrackArtworkView(track: track, size: 36)
                .environmentObject(app)
            VStack(alignment: .leading, spacing: 2) {
                Text(track.title)
                    .font(.subheadline.weight(isCurrent ? .bold : .regular))
                    .lineLimit(1)
                Text(track.displayArtist)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer()
            if isCurrent {
                Image(systemName: "speaker.wave.2.fill")
                    .foregroundStyle(.blue)
            } else {
                Button {
                    app.removeFromQueue(track)
                } label: {
                    Image(systemName: "minus.circle")
                }
                .buttonStyle(.plain)
            }
        }
        .contentShape(Rectangle())
        .onTapGesture {
            app.play(track, queue: app.queueTracks, updateQueue: false)
        }
    }
}

// MARK: - Settings View

struct SettingsView: View {
    @EnvironmentObject private var app: AppState

    var body: some View {
        Form {
            Section("Backend") {
                TextField("192.168.1.50:8000", text: $app.apiEndpoint)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()

                if let status = app.connectionStatus {
                    Text(status)
                        .font(.footnote)
                        .foregroundStyle(status.lowercased().contains("connected") ? .green : .red)
                }

                Button {
                    Task { await app.testConnection() }
                } label: {
                    if app.isTestingConnection {
                        ProgressView()
                    } else {
                        Text("Test connection")
                    }
                }

                Button("Refresh library") {
                    Task { await app.refreshLibrary() }
                }
            }

            AccountSection()

            Section("Detected endpoint") {
                Text(app.normalizedEndpoint.isEmpty ? "Not set" : app.normalizedEndpoint)
                    .font(.footnote.monospaced())
                    .textSelection(.enabled)
            }

            Section("Indexers") {
                SecureField("Prowlarr API key", text: $app.prowlarrApiKey)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                Text(app.prowlarrApiKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                      ? "Using backend .env key"
                      : "Using this device key")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }

            Section("Playback") {
                Toggle(isOn: $app.autoplaySimilarEnabled) {
                    Label("Autoplay Similar Songs", systemImage: "infinity")
                }
            }
        }
        .formStyle(.grouped)
    }
}

// MARK: - Mini Queue Track

struct QueueMiniTrack: View {
    @EnvironmentObject private var app: AppState
    let track: ApiTrack
    let isCurrent: Bool

    var body: some View {
        HStack(spacing: 8) {
            TrackArtworkView(track: track, size: 32)
                .environmentObject(app)
            VStack(alignment: .leading, spacing: 1) {
                Text(track.title)
                    .font(.caption)
                    .lineLimit(1)
                Text(track.displayArtist)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer()
            if isCurrent {
                Image(systemName: "speaker.wave.2.fill")
                    .font(.caption2)
                    .foregroundStyle(.blue)
            }
        }
        .padding(4)
        .contentShape(Rectangle())
        .onTapGesture {
            app.play(track, queue: app.queueTracks, updateQueue: false)
        }
    }
}

// MARK: - Album Artwork View

struct AlbumArtworkView: View {
    @EnvironmentObject private var app: AppState
    let album: Album
    let size: CGFloat

    var body: some View {
        Group {
            if let image = app.albumCovers[album.id] {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFill()
            } else {
                LinearGradient(
                    colors: [.blue.opacity(0.7), .purple.opacity(0.55)],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
                .overlay(Image(systemName: "music.note").font(.title).foregroundStyle(.white.opacity(0.6)))
            }
        }
        .frame(width: size, height: size)
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
    }
}

// MARK: - Track Artwork View

struct TrackArtworkView: View {
    @EnvironmentObject private var app: AppState
    let track: ApiTrack
    let size: CGFloat

    var body: some View {
        Group {
            if let image = app.coverImage(for: track) {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFill()
            } else {
                LinearGradient(
                    colors: [.blue.opacity(0.55), .purple.opacity(0.45)],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
                .overlay(Image(systemName: "music.note").foregroundStyle(.white.opacity(0.6)))
            }
        }
        .frame(width: size, height: size)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}

// MARK: - Track Row (macOS-adapted)

struct TrackRowNative: View {
    @EnvironmentObject private var app: AppState
    @State private var showingMenu = false
    let track: ApiTrack

    var body: some View {
        HStack(spacing: 12) {
            Text("\(app.trackListIndex(for: track) + 1)")
                .font(.caption.monospacedDigit())
                .foregroundStyle(.tertiary)
                .frame(width: 24)

            TrackArtworkView(track: track, size: 42)
                .environmentObject(app)

            VStack(alignment: .leading, spacing: 3) {
                Text(track.title)
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(1)
                Text("\(track.displayArtist) · \(track.displayAlbum)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            Spacer()

            Text(track.durationText)
                .font(.caption.monospacedDigit())
                .foregroundStyle(.secondary)

            Button {} label: {
                Image(systemName: "ellipsis")
                    .foregroundStyle(.secondary)
            }
            .buttonStyle(.plain)
            .menu {
                Button { app.addToQueue(track) } label: {
                    Label("Add to Queue", systemImage: "text.badge.plus")
                }
                Button { Task { await app.toggleLike(track) } } label: {
                    Label(app.likedTrackIds.contains(track.id) ? "Unlike" : "Like",
                          systemImage: app.likedTrackIds.contains(track.id) ? "heart.slash" : "heart")
                }
            }
            .menuStyle(.borderlessButton)
        }
        .contentShape(Rectangle())
        .onTapGesture {
            app.play(track)
        }
        .background(app.currentTrack?.id == track.id ? Color.blue.opacity(0.18) : Color.clear)
        .cornerRadius(10)
    }
}

// MARK: - Album Row

struct AlbumRow: View {
    @EnvironmentObject private var app: AppState
    let album: Album

    var body: some View {
        VStack(spacing: 8) {
            AlbumArtworkView(album: album, size: 140)
                .environmentObject(app)
            VStack(spacing: 2) {
                Text(album.title)
                    .font(.subheadline.weight(.medium))
                    .lineLimit(1)
                    .multilineTextAlignment(.center)
                Text(album.artist)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .multilineTextAlignment(.center)
            }
        }
        .frame(width: 140)
    }
}
