import SwiftUI

struct RootView: View {
    @EnvironmentObject private var app: AppState
    @FocusState private var searchFocused: Bool

    var body: some View {
        ZStack {
            LinearGradient(colors: [Color(red: 0.04, green: 0.06, blue: 0.10), Color(red: 0.02, green: 0.03, blue: 0.06)], startPoint: .top, endPoint: .bottom)
                .ignoresSafeArea()

            VStack(spacing: 0) {
                searchHeader

                if let warning = app.endpointWarning, app.selectedTab == .settings {
                    Text(warning)
                        .font(.footnote)
                        .foregroundStyle(.black)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.yellow.opacity(0.85))
                        .clipShape(RoundedRectangle(cornerRadius: 14))
                        .padding(.horizontal)
                        .padding(.bottom, 8)
                }

                if let error = app.errorMessage {
                    Text(error)
                        .font(.footnote)
                        .foregroundStyle(.white)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.red.opacity(0.35))
                        .clipShape(RoundedRectangle(cornerRadius: 14))
                        .padding(.horizontal)
                        .padding(.bottom, 8)
                }

                content
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .contentShape(Rectangle())
                    .simultaneousGesture(TapGesture().onEnded { dismissSearch() })

                PlayerBar()
                    .environmentObject(app)
                    .contentShape(Rectangle())
                    .simultaneousGesture(TapGesture().onEnded { dismissSearch() })

                tabBar
                    .contentShape(Rectangle())
                    .simultaneousGesture(TapGesture().onEnded { dismissSearch() })
            }
        }
        .task { await app.refreshLibrary() }
        .onChange(of: app.searchText) { _ in
            guard app.searchMode == .torrent else { return }
            Task {
                try? await Task.sleep(nanoseconds: 350_000_000)
                await app.searchTorrents()
            }
        }
        .onChange(of: app.searchMode) { mode in
            if mode == .torrent {
                app.selectedAlbumId = nil
                Task { await app.searchTorrents() }
            }
        }
        .onChange(of: app.selectedTab) { tab in
            if tab != .albums { app.selectedAlbumId = nil }
        }
    }

    private var searchHeader: some View {
        VStack(spacing: 10) {
            HStack(spacing: 10) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.secondary)
                TextField(app.searchMode == .torrent ? "Search torrents…" : app.selectedTab == .albums ? "Search albums…" : "Search library…", text: $app.searchText)
                    .focused($searchFocused)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .submitLabel(.search)
                    .onSubmit {
                        dismissSearch()
                        if app.searchMode == .torrent { Task { await app.searchTorrents() } }
                    }
                if !app.searchText.isEmpty {
                    Button {
                        app.searchText = ""
                        app.torrents = []
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .padding(12)
            .background(Color.white.opacity(0.08))
            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))

            if searchFocused || !app.searchText.isEmpty || app.searchMode == .torrent {
                Picker("Search mode", selection: $app.searchMode) {
                    ForEach(SearchMode.allCases) { mode in
                        Text(mode.rawValue).tag(mode)
                    }
                }
                .pickerStyle(.segmented)
                .transition(.move(edge: .top).combined(with: .opacity))
            }
        }
        .animation(.easeInOut(duration: 0.18), value: searchFocused)
        .animation(.easeInOut(duration: 0.18), value: app.searchText.isEmpty)
        .padding(.horizontal)
        .padding(.top, 10)
        .padding(.bottom, 10)
        .background(.ultraThinMaterial)
    }

    @ViewBuilder
    private var content: some View {
        if app.searchMode == .torrent {
            TorrentSearchView()
                .environmentObject(app)
        } else {
            switch app.selectedTab {
            case .library, .liked:
                LibraryView()
                    .environmentObject(app)
            case .albums:
                AlbumsView()
                    .environmentObject(app)
            case .settings:
                SettingsView()
                    .environmentObject(app)
            }
        }
    }

    private var tabBar: some View {
        HStack(spacing: 6) {
            ForEach(MusicTab.allCases) { tab in
                Button {
                    dismissSearch()
                    app.searchMode = .library
                    app.selectedTab = tab
                    if tab != .albums { app.selectedAlbumId = nil }
                } label: {
                    VStack(spacing: 4) {
                        Image(systemName: icon(for: tab))
                            .font(.system(size: 17, weight: .semibold))
                        Text(tab.rawValue)
                            .font(.caption2.weight(.semibold))
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 8)
                    .foregroundStyle(app.selectedTab == tab ? Color.blue : Color.secondary)
                    .background(app.selectedTab == tab ? Color.blue.opacity(0.16) : Color.clear)
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                }
            }
        }
        .padding(.horizontal, 10)
        .padding(.top, 8)
        .padding(.bottom, 10)
        .background(.ultraThinMaterial)
    }

    private func dismissSearch() {
        searchFocused = false
    }

    private func icon(for tab: MusicTab) -> String {
        switch tab {
        case .library:
            return "music.note.list"
        case .albums:
            return "square.grid.2x2.fill"
        case .liked:
            return "heart.fill"
        case .settings:
            return "gearshape.fill"
        }
    }
}

struct LibraryView: View {
    @EnvironmentObject private var app: AppState

    var body: some View {
        ScrollView {
            LazyVStack(spacing: 10) {
                HStack {
                    Text(app.selectedTab == .liked ? "Liked Songs" : "Your Library")
                        .font(.title2.bold())
                    Spacer()
                    if app.isLoading { ProgressView() }
                }
                .padding(.horizontal)
                .padding(.top, 12)

                if app.filteredTracks.isEmpty {
                    ContentUnavailableView(app.canUseApi ? "No tracks" : "Connect API", systemImage: app.canUseApi ? "music.note" : "wifi.exclamationmark", description: Text(app.canUseApi ? "Import music on the backend or try another search." : "Open Settings and set endpoint + token."))
                        .foregroundStyle(.secondary)
                        .padding(.top, 48)
                } else {
                    ForEach(app.filteredTracks) { track in
                        TrackRowNative(track: track)
                            .environmentObject(app)
                            .padding(.horizontal)
                    }
                }
            }
            .padding(.bottom, 10)
        }
        .refreshable { await app.refreshLibrary() }
    }
}

struct AlbumsView: View {
    @EnvironmentObject private var app: AppState

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 14) {
                HStack {
                    Button { app.selectedAlbumId = nil } label: {
                        if app.selectedAlbumId != nil {
                            Label("Albums", systemImage: "chevron.left")
                                .font(.subheadline.weight(.semibold))
                        }
                    }
                    .buttonStyle(.plain)

                    Text(app.selectedAlbum?.title ?? "Albums")
                        .font(.title2.bold())
                        .lineLimit(1)

                    Spacer()
                    if app.isLoading { ProgressView() }
                }
                .padding(.horizontal)
                .padding(.top, 12)

                if let album = app.selectedAlbum {
                    AlbumDetailView(album: album)
                        .environmentObject(app)
                } else if app.filteredAlbums.isEmpty {
                    ContentUnavailableView(app.canUseApi ? "No albums" : "Connect API", systemImage: app.canUseApi ? "square.grid.2x2" : "wifi.exclamationmark", description: Text(app.canUseApi ? "Albums will appear after library refresh." : "Open Settings and set endpoint + token."))
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity)
                        .padding(.top, 48)
                } else {
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 14) {
                        ForEach(app.filteredAlbums) { album in
                            AlbumCardNative(album: album)
                                .environmentObject(app)
                        }
                    }
                    .padding(.horizontal)
                }
            }
            .padding(.bottom, 10)
        }
        .refreshable { await app.refreshLibrary() }
        .task { await app.loadMissingAlbumCovers() }
    }
}

struct AlbumDetailView: View {
    @EnvironmentObject private var app: AppState
    let album: Album

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .bottom, spacing: 16) {
                AlbumArtworkView(album: album, size: 132)
                    .environmentObject(app)
                VStack(alignment: .leading, spacing: 6) {
                    Text(album.title)
                        .font(.title2.bold())
                        .lineLimit(2)
                    Text(album.artist)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                    Text(album.trackCountText)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    HStack(spacing: 10) {
                        Button {
                            if let first = album.tracks.first { app.play(first, queue: album.tracks) }
                        } label: {
                            Label("Play", systemImage: "play.fill")
                        }
                        .buttonStyle(.borderedProminent)

                        Button {
                            if let first = album.tracks.first {
                                let previousShuffle = app.shuffleEnabled
                                if !app.shuffleEnabled { app.shuffleEnabled = true }
                                app.play(first, queue: album.tracks)
                                app.shuffleEnabled = previousShuffle || app.shuffleEnabled
                            }
                        } label: {
                            Image(systemName: "shuffle")
                        }
                        .buttonStyle(.bordered)
                    }
                    .padding(.top, 6)
                }
            }
            .padding(.horizontal)

            LazyVStack(spacing: 10) {
                ForEach(album.tracks) { track in
                    TrackRowNative(track: track)
                        .environmentObject(app)
                }
            }
            .padding(.horizontal)
        }
    }
}

struct AlbumCardNative: View {
    @EnvironmentObject private var app: AppState
    let album: Album

    var body: some View {
        Button { app.selectedAlbumId = album.id } label: {
            VStack(alignment: .leading, spacing: 9) {
                AlbumArtworkView(album: album, size: nil)
                    .environmentObject(app)
                    .aspectRatio(1, contentMode: .fit)
                Text(album.title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.white)
                    .lineLimit(1)
                Text("\(album.artist) · \(album.trackCountText)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            .padding(10)
            .background(Color.white.opacity(0.06))
            .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        }
        .buttonStyle(.plain)
    }
}

struct AlbumArtworkView: View {
    @EnvironmentObject private var app: AppState
    let album: Album
    let size: CGFloat?

    var body: some View {
        Group {
            if let image = app.albumCovers[album.id] {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFill()
            } else {
                LinearGradient(colors: [.blue.opacity(0.7), .purple.opacity(0.55)], startPoint: .topLeading, endPoint: .bottomTrailing)
                    .overlay(Image(systemName: "music.note").font(.title).foregroundStyle(.white))
            }
        }
        .frame(width: size, height: size)
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
    }
}

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
                LinearGradient(colors: [.blue.opacity(0.55), .purple.opacity(0.45)], startPoint: .topLeading, endPoint: .bottomTrailing)
                    .overlay(Image(systemName: "music.note").foregroundStyle(.white))
            }
        }
        .frame(width: size, height: size)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}

struct TrackRowNative: View {
    @EnvironmentObject private var app: AppState
    @State private var dragOffset: CGFloat = 0
    let track: ApiTrack

    var body: some View {
        ZStack(alignment: .trailing) {
            Label("Queue", systemImage: "text.badge.plus")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.white)
                .padding(.horizontal, 14)
                .frame(maxHeight: .infinity)
                .opacity(dragOffset < -8 ? 1 : 0)

            HStack(spacing: 12) {
                TrackArtworkView(track: track, size: 52)
                    .environmentObject(app)

                VStack(alignment: .leading, spacing: 4) {
                    Text(track.title)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.white)
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

                Menu {
                    Button {
                        app.addToQueue(track)
                    } label: {
                        Label("Add to Queue", systemImage: "text.badge.plus")
                    }
                    Button {
                        Task { await app.toggleLike(track) }
                    } label: {
                        Label(app.likedTrackIds.contains(track.id) ? "Unlike" : "Like", systemImage: app.likedTrackIds.contains(track.id) ? "heart.slash" : "heart")
                    }
                } label: {
                    Image(systemName: "ellipsis")
                        .foregroundStyle(.secondary)
                        .frame(width: 28, height: 28)
                }
            }
            .padding(12)
            .background(app.currentTrack?.id == track.id ? Color.blue.opacity(0.18) : Color.white.opacity(0.06))
            .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
            .offset(x: dragOffset)
        }
        .background(Color.blue.opacity(dragOffset < 0 ? 0.8 : 0))
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .contentShape(Rectangle())
        .onTapGesture {
            app.play(track)
        }
        .simultaneousGesture(
            DragGesture(minimumDistance: 24)
                .onChanged { value in
                    guard value.translation.width < 0,
                          abs(value.translation.width) > abs(value.translation.height) * 1.2 else { return }
                    dragOffset = max(value.translation.width, -96)
                }
                .onEnded { value in
                    let shouldAddToQueue = value.translation.width < -70
                        && abs(value.translation.width) > abs(value.translation.height) * 1.2
                    if shouldAddToQueue {
                        app.addToQueue(track)
                    }
                    withAnimation(.spring(response: 0.25, dampingFraction: 0.85)) {
                        dragOffset = 0
                    }
                }
        )
        .accessibilityAction(named: "Add to Queue") {
            app.addToQueue(track)
        }
    }
}

struct TorrentSearchView: View {
    @EnvironmentObject private var app: AppState

    var body: some View {
        ScrollView {
            LazyVStack(spacing: 10) {
                HStack {
                    Text(app.searchText.isEmpty ? "Torrent Search" : "Torrent Results")
                        .font(.title2.bold())
                    Spacer()
                    if app.isSearchingTorrents { ProgressView() }
                }
                .padding(.horizontal)
                .padding(.top, 12)

                if app.searchText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    ContentUnavailableView("Search torrents", systemImage: "magnifyingglass", description: Text("Type an artist, album, or song above."))
                        .foregroundStyle(.secondary)
                        .padding(.top, 48)
                } else if app.torrents.isEmpty && !app.isSearchingTorrents {
                    ContentUnavailableView("No torrent results", systemImage: "tray", description: Text("Try a different query."))
                        .foregroundStyle(.secondary)
                        .padding(.top, 48)
                } else {
                    ForEach(app.torrents) { torrent in
                        TorrentRowNative(torrent: torrent)
                            .environmentObject(app)
                            .padding(.horizontal)
                    }
                }
            }
        }
        .refreshable { await app.searchTorrents() }
    }
}

struct TorrentRowNative: View {
    @EnvironmentObject private var app: AppState
    @StateObject private var importController = TorrentImportController()
    let torrent: TorrentResult

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(torrent.name)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.white)
                        .lineLimit(2)
                    Text("\(torrent.source.displayName) · \(torrent.uploader ?? "unknown") · \(torrent.sizeText) · S \(torrent.seeders ?? "0")")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button {
                    Task { await importController.start(torrent: torrent, app: app) }
                } label: {
                    if importController.isRunning {
                        ProgressView()
                            .tint(.white)
                    } else {
                        Text(importController.progress?.isFailure == true ? "Retry" : "Import")
                            .font(.caption.weight(.bold))
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(importController.isRunning)
            }

            if let progress = importController.progress {
                TorrentImportProgressView(progress: progress)
            }
        }
        .padding(12)
        .background(Color.white.opacity(0.06))
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .animation(.easeInOut(duration: 0.2), value: importController.progress)
    }
}

struct TorrentImportProgressView: View {
    let progress: TorrentImportProgressState

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack {
                Text(progress.status)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(progress.isFailure ? .red : .secondary)
                Spacer()
                Text(progress.percentText)
                    .font(.caption.monospacedDigit().weight(.semibold))
                    .foregroundStyle(.secondary)
            }

            ProgressView(value: progress.clampedProgress)
                .tint(progress.isFailure ? .red : .blue)
                .controlSize(.regular)

            Text(progress.details)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(2)
        }
        .padding(10)
        .background(Color.black.opacity(0.18))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

struct PlayerBar: View {
    @EnvironmentObject private var app: AppState
    @State private var showingQueue = false

    var body: some View {
        VStack(spacing: 10) {
            ProgressView(value: app.playbackProgress)
                .tint(.blue)

            HStack(spacing: 10) {
                Button { app.toggleShuffle() } label: {
                    Image(systemName: "shuffle")
                        .foregroundStyle(app.shuffleEnabled ? .blue : .secondary)
                }
                .accessibilityLabel("Shuffle")

                Spacer()

                Text(app.repeatMode.label)
                    .font(.caption2)
                    .foregroundStyle(.secondary)

                Spacer()

                Button { app.cycleRepeatMode() } label: {
                    Image(systemName: app.repeatMode.iconName)
                        .foregroundStyle(app.repeatMode.isActive ? .blue : .secondary)
                }
                .accessibilityLabel(app.repeatMode.label)
            }
            .padding(.horizontal, 4)

            HStack(spacing: 12) {
                if let track = app.currentTrack {
                    TrackArtworkView(track: track, size: 46)
                        .environmentObject(app)
                } else {
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .fill(LinearGradient(colors: [.blue.opacity(0.7), .purple.opacity(0.55)], startPoint: .topLeading, endPoint: .bottomTrailing))
                        .frame(width: 46, height: 46)
                        .overlay(Image(systemName: "music.note").foregroundStyle(.white))
                }

                VStack(alignment: .leading, spacing: 3) {
                    Text(app.currentTrack?.title ?? "Nothing playing")
                        .font(.subheadline.weight(.semibold))
                        .lineLimit(1)
                    Text(app.currentTrack?.displayArtist ?? "Choose a song")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }

                Spacer()

                Button { app.previousTrack() } label: { Image(systemName: "backward.fill") }
                Button { app.togglePlayback() } label: {
                    Image(systemName: app.isPlaying ? "pause.fill" : "play.fill")
                        .font(.title3.weight(.bold))
                        .frame(width: 42, height: 42)
                        .background(Color.blue)
                        .foregroundStyle(.white)
                        .clipShape(Circle())
                }
                Button { app.nextTrack() } label: { Image(systemName: "forward.fill") }
                Button { showingQueue = true } label: {
                    Image(systemName: "list.bullet")
                }
                .accessibilityLabel("Queue")
            }
            .foregroundStyle(.white)
        }
        .padding(.horizontal)
        .padding(.top, 10)
        .padding(.bottom, 12)
        .background(.ultraThinMaterial)
        .sheet(isPresented: $showingQueue) {
            QueueSheetView()
                .environmentObject(app)
                .presentationDetents([.medium, .large])
        }
    }
}

struct QueueSheetView: View {
    @EnvironmentObject private var app: AppState
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section {
                    HStack {
                        Label(app.shuffleEnabled ? "Shuffle On" : "Shuffle Off", systemImage: "shuffle")
                            .foregroundStyle(app.shuffleEnabled ? .blue : .primary)
                        Spacer()
                        Button(app.shuffleEnabled ? "Turn Off" : "Turn On") {
                            app.toggleShuffle()
                        }
                    }

                    HStack {
                        Label(app.repeatMode.label, systemImage: app.repeatMode.iconName)
                            .foregroundStyle(app.repeatMode.isActive ? .blue : .primary)
                        Spacer()
                        Button("Change") {
                            app.cycleRepeatMode()
                        }
                    }

                    Button(role: .destructive) {
                        app.clearQueue()
                    } label: {
                        Label("Clear Upcoming Queue", systemImage: "trash")
                    }
                }

                Section("Now Playing") {
                    if let currentTrack = app.currentTrack {
                        QueueTrackRow(track: currentTrack, isCurrent: true)
                            .environmentObject(app)
                    } else {
                        Text("Nothing playing")
                            .foregroundStyle(.secondary)
                    }
                }

                Section("Up Next") {
                    if app.upcomingQueueTracks.isEmpty {
                        Text("No upcoming tracks")
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(app.upcomingQueueTracks) { track in
                            QueueTrackRow(track: track, isCurrent: false)
                                .environmentObject(app)
                        }
                    }
                }
            }
            .navigationTitle("Queue")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}

struct QueueTrackRow: View {
    @EnvironmentObject private var app: AppState
    let track: ApiTrack
    let isCurrent: Bool

    var body: some View {
        HStack(spacing: 12) {
            TrackArtworkView(track: track, size: 42)
                .environmentObject(app)
            VStack(alignment: .leading, spacing: 3) {
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
                Button(role: .destructive) {
                    app.removeFromQueue(track)
                } label: {
                    Image(systemName: "minus.circle")
                }
            }
        }
        .contentShape(Rectangle())
        .onTapGesture {
            app.play(track, queue: app.queueTracks, updateQueue: false)
        }
    }
}

struct SettingsView: View {
    @EnvironmentObject private var app: AppState

    var body: some View {
        Form {
            Section("Backend") {
                TextField("192.168.1.50:8000", text: $app.apiEndpoint)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)
                SecureField("API_TOKEN", text: $app.apiToken)
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

            Section("Detected endpoint") {
                Text(app.normalizedEndpoint.isEmpty ? "Not set" : app.normalizedEndpoint)
                    .font(.footnote.monospaced())
                    .textSelection(.enabled)
            }

            Section("Playback") {
                Toggle(isOn: $app.autoplaySimilarEnabled) {
                    Label("Autoplay Similar Songs", systemImage: "infinity")
                }
            }

            Section("Tip") {
                Text("For iPhone + backend on your computer/server, use the LAN IP, for example 192.168.1.50:8000. localhost on iPhone means the iPhone itself, not your Mac.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
        .scrollContentBackground(.hidden)
        .background(Color.clear)
    }
}
