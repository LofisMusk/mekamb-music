import SwiftUI
import UIKit

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
                    .layoutPriority(1)
                    .contentShape(Rectangle())

                PlayerBar()
                    .environmentObject(app)
                    .contentShape(Rectangle())
                    .simultaneousGesture(TapGesture().onEnded { dismissSearch() })

                tabBar
                    .contentShape(Rectangle())
                    .simultaneousGesture(TapGesture().onEnded { dismissSearch() })
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task { await app.refreshLibrary() }
        .onChange(of: app.searchText) { _, _ in
            guard app.searchMode.searchesRemoteSources else { return }
            Task {
                try? await Task.sleep(nanoseconds: 350_000_000)
                await app.searchTorrents()
            }
        }
        .onChange(of: app.searchMode) { _, mode in
            if mode.searchesRemoteSources {
                app.selectedAlbumId = nil
                app.torrents = []
                Task { await app.searchTorrents() }
            }
        }
        .onChange(of: app.selectedTab) { _, tab in
            if tab != .albums { app.selectedAlbumId = nil }
            if tab != .playlists { app.selectedPlaylistId = nil }
        }
    }

    private var searchHeader: some View {
        VStack(spacing: 10) {
            HStack(spacing: 10) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.secondary)
                TextField(searchPlaceholder, text: $app.searchText)
                    .focused($searchFocused)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .submitLabel(.search)
                    .onSubmit {
                        dismissSearch()
                        if app.searchMode.searchesRemoteSources { Task { await app.searchTorrents() } }
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

            if searchFocused || !app.searchText.isEmpty || app.searchMode.searchesRemoteSources {
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
        if app.searchMode.searchesRemoteSources {
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
            case .playlists:
                PlaylistsView()
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
                    if tab != .playlists { app.selectedPlaylistId = nil }
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

    private var searchPlaceholder: String {
        switch app.searchMode {
        case .torrent:
            return "Search torrents..."
        case .indexer:
            return "Search indexers..."
        case .library:
            if app.selectedTab == .albums { return "Search albums..." }
            if app.selectedTab == .playlists { return "Search playlists..." }
            return "Search library..."
        }
    }

    private func icon(for tab: MusicTab) -> String {
        switch tab {
        case .library:
            return "music.note.list"
        case .albums:
            return "square.grid.2x2.fill"
        case .playlists:
            return "list.bullet.rectangle.fill"
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
            LazyVStack(alignment: .leading, spacing: 22) {
                HStack {
                    Text(app.selectedTab == .liked ? "Liked Songs" : "Made For You")
                        .font(.title2.bold())
                    Spacer()
                    if app.isLoading { ProgressView() }
                }
                .padding(.horizontal)
                .padding(.top, 12)

                if app.selectedTab == .liked {
                    likedSongsContent
                } else if app.tracks.isEmpty {
                    ContentUnavailableView(app.canUseApi ? "No tracks" : "Connect API", systemImage: app.canUseApi ? "music.note" : "wifi.exclamationmark", description: Text(app.canUseApi ? "Import music on the backend or try another search." : "Open Settings and set endpoint + token."))
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity)
                        .padding(.top, 48)
                } else if !app.searchText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    TrackShelfView(title: "Search Results", tracks: Array(app.filteredTracks.prefix(24)))
                        .environmentObject(app)
                } else {
                    homeContent
                }
            }
            .padding(.bottom, 24)
        }
        .refreshable { await app.refreshLibrary() }
    }

    @ViewBuilder
    private var likedSongsContent: some View {
        if app.filteredTracks.isEmpty {
            ContentUnavailableView("No liked tracks", systemImage: "heart", description: Text("Heart songs from your library to build this collection."))
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity)
                .padding(.top, 48)
        } else {
            LazyVStack(spacing: 10) {
                ForEach(app.filteredTracks) { track in
                    TrackRowNative(track: track)
                        .environmentObject(app)
                        .padding(.horizontal)
                }
            }
        }
    }

    private var homeContent: some View {
        VStack(alignment: .leading, spacing: 22) {
            DailyMixShelfView(mixes: app.dailyMixes)
                .environmentObject(app)

            TrackShelfView(title: "Recommended For You", tracks: app.homeRecommendedTracks)
                .environmentObject(app)

            TrackShelfView(title: "Recently Added", tracks: app.recentlyAddedTracks)
                .environmentObject(app)

            if !app.downloadedTracks.isEmpty {
                TrackShelfView(title: "Available Offline", tracks: app.downloadedTracks)
                    .environmentObject(app)
            }

            if !app.likedTracksPreview.isEmpty {
                TrackShelfView(title: "Your Liked Mix", tracks: app.likedTracksPreview)
                    .environmentObject(app)
            }
        }
    }
}

struct DailyMixShelfView: View {
    @EnvironmentObject private var app: AppState
    let mixes: [DailyMix]

    var body: some View {
        if !mixes.isEmpty {
            VStack(alignment: .leading, spacing: 12) {
                Text("Daily Mixes")
                    .font(.headline)
                    .padding(.horizontal)

                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(alignment: .top, spacing: 14) {
                        ForEach(mixes) { mix in
                            DailyMixCard(mix: mix)
                                .environmentObject(app)
                        }
                    }
                    .padding(.horizontal)
                }
            }
        }
    }
}

struct DailyMixCard: View {
    @EnvironmentObject private var app: AppState
    let mix: DailyMix

    var body: some View {
        Button {
            if let first = mix.tracks.first {
                app.play(first, queue: mix.tracks)
            }
        } label: {
            VStack(alignment: .leading, spacing: 8) {
                ZStack(alignment: .bottomLeading) {
                    if let firstTrack = mix.tracks.first {
                        TrackArtworkView(track: firstTrack, size: 156)
                            .environmentObject(app)
                    } else {
                        LinearGradient(colors: [.green.opacity(0.65), .blue.opacity(0.55)], startPoint: .topLeading, endPoint: .bottomTrailing)
                            .frame(width: 156, height: 156)
                            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                    }

                    Image(systemName: "play.fill")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.black)
                        .padding(8)
                        .background(Color.white)
                        .clipShape(Circle())
                        .padding(10)
                }

                Text(mix.title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.white)
                    .lineLimit(1)
                Text(mix.description)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                    .frame(height: 34, alignment: .topLeading)
            }
            .frame(width: 156, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

struct TrackShelfView: View {
    @EnvironmentObject private var app: AppState
    let title: String
    let tracks: [ApiTrack]

    var body: some View {
        if !tracks.isEmpty {
            VStack(alignment: .leading, spacing: 12) {
                Text(title)
                    .font(.headline)
                    .padding(.horizontal)

                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(alignment: .top, spacing: 14) {
                        ForEach(tracks) { track in
                            TrackRecommendationCard(track: track)
                                .environmentObject(app)
                        }
                    }
                    .padding(.horizontal)
                }
            }
        }
    }
}

struct AlbumShelfView: View {
    @EnvironmentObject private var app: AppState
    let title: String
    let albums: [Album]

    var body: some View {
        if !albums.isEmpty {
            VStack(alignment: .leading, spacing: 12) {
                Text(title)
                    .font(.headline)
                    .padding(.horizontal)

                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(alignment: .top, spacing: 14) {
                        ForEach(albums) { album in
                            AlbumRecommendationCard(album: album)
                                .environmentObject(app)
                        }
                    }
                    .padding(.horizontal)
                }
            }
        }
    }
}

struct TrackRecommendationCard: View {
    @EnvironmentObject private var app: AppState
    let track: ApiTrack

    var body: some View {
        Button {
            app.play(track)
        } label: {
            VStack(alignment: .leading, spacing: 8) {
                TrackArtworkView(track: track, size: 132)
                    .environmentObject(app)
                Text(track.title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.white)
                    .lineLimit(2)
                    .frame(height: 38, alignment: .topLeading)
                Text(track.displayArtist)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            .frame(width: 132, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

struct AlbumRecommendationCard: View {
    @EnvironmentObject private var app: AppState
    let album: Album

    var body: some View {
        Button {
            app.selectedTab = .albums
            app.selectedAlbumId = album.id
        } label: {
            VStack(alignment: .leading, spacing: 8) {
                AlbumArtworkView(album: album, size: 132)
                    .environmentObject(app)
                Text(album.title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.white)
                    .lineLimit(2)
                    .frame(height: 38, alignment: .topLeading)
                Text("\(album.artist) • \(album.trackCountText)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            .frame(width: 132, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
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

                        Button {
                            Task { await app.downloadAlbum(album) }
                        } label: {
                            if app.downloadingAlbumIds.contains(album.id) {
                                ProgressView()
                            } else {
                                Label(
                                    app.isAlbumAvailableOffline(album) ? "Offline" : "Download",
                                    systemImage: app.isAlbumAvailableOffline(album) ? "arrow.down.circle.fill" : "arrow.down.circle"
                                )
                            }
                        }
                        .buttonStyle(.bordered)
                        .disabled(app.downloadingAlbumIds.contains(album.id) || app.isAlbumAvailableOffline(album))

                        if app.downloadedTrackCount(in: album) > 0 {
                            Button(role: .destructive) {
                                app.removeDownloadedAlbum(album)
                            } label: {
                                Label("Remove", systemImage: "trash")
                            }
                            .buttonStyle(.bordered)
                        }

                        Button(role: .destructive) {
                            Task { await app.deleteAlbum(album) }
                        } label: {
                            Label("Delete", systemImage: "trash")
                        }
                        .buttonStyle(.bordered)
                        .disabled(app.isLoading)
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
                ZStack(alignment: .topTrailing) {
                    AlbumArtworkView(album: album, size: nil)
                        .environmentObject(app)
                        .aspectRatio(1, contentMode: .fit)

                    if app.isAlbumAvailableOffline(album) {
                        Image(systemName: "arrow.down.circle.fill")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(.white)
                            .padding(6)
                            .background(Color.blue.opacity(0.9))
                            .clipShape(Circle())
                            .padding(7)
                    }
                }
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

struct PlaylistsView: View {
    @EnvironmentObject private var app: AppState
    @State private var showingCreatePlaylist = false
    @State private var newPlaylistName = ""

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 14) {
                HStack {
                    Button { app.selectedPlaylistId = nil } label: {
                        if app.selectedPlaylistId != nil {
                            Label("Playlists", systemImage: "chevron.left")
                                .font(.subheadline.weight(.semibold))
                        }
                    }
                    .buttonStyle(.plain)

                    Text(app.selectedPlaylist?.name ?? "Playlists")
                        .font(.title2.bold())
                        .lineLimit(1)

                    Spacer()

                    if app.isLoading {
                        ProgressView()
                    } else if app.selectedPlaylistId == nil {
                        Button {
                            newPlaylistName = ""
                            showingCreatePlaylist = true
                        } label: {
                            Image(systemName: "plus.circle.fill")
                                .font(.title3)
                        }
                        .accessibilityLabel("Create Playlist")
                    }
                }
                .padding(.horizontal)
                .padding(.top, 12)

                if let playlist = app.selectedPlaylist {
                    PlaylistDetailView(playlist: playlist)
                        .environmentObject(app)
                } else if app.filteredPlaylists.isEmpty {
                    ContentUnavailableView(app.canUseApi ? "No playlists" : "Connect API", systemImage: app.canUseApi ? "music.note.list" : "wifi.exclamationmark", description: Text(app.canUseApi ? "Create a playlist or add songs from track menus." : "Open Settings and set endpoint + token."))
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity)
                        .padding(.top, 48)
                } else {
                    LazyVStack(spacing: 10) {
                        ForEach(app.filteredPlaylists) { playlist in
                            PlaylistCardNative(playlist: playlist)
                                .environmentObject(app)
                        }
                    }
                    .padding(.horizontal)
                }
            }
            .padding(.bottom, 10)
        }
        .refreshable { await app.refreshLibrary() }
        .alert("New Playlist", isPresented: $showingCreatePlaylist) {
            TextField("Playlist name", text: $newPlaylistName)
            Button("Create") {
                Task { await app.createPlaylist(named: newPlaylistName) }
            }
            Button("Cancel", role: .cancel) {}
        }
    }
}

struct PlaylistCardNative: View {
    @EnvironmentObject private var app: AppState
    let playlist: PlaylistDetail

    var body: some View {
        Button {
            app.selectedPlaylistId = playlist.id
        } label: {
            HStack(spacing: 12) {
                ZStack {
                    LinearGradient(colors: [.green.opacity(0.65), .blue.opacity(0.55)], startPoint: .topLeading, endPoint: .bottomTrailing)
                    Image(systemName: "music.note.list")
                        .font(.title2.weight(.semibold))
                        .foregroundStyle(.white)
                }
                .frame(width: 58, height: 58)
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))

                VStack(alignment: .leading, spacing: 4) {
                    Text(playlist.name)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.white)
                        .lineLimit(1)
                    Text(playlist.trackCountText)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.secondary)
            }
            .padding(12)
            .background(Color.white.opacity(0.06))
            .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        }
        .buttonStyle(.plain)
    }
}

struct PlaylistDetailView: View {
    @EnvironmentObject private var app: AppState
    let playlist: PlaylistDetail

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .bottom, spacing: 16) {
                ZStack {
                    LinearGradient(colors: [.green.opacity(0.65), .blue.opacity(0.55)], startPoint: .topLeading, endPoint: .bottomTrailing)
                    Image(systemName: "music.note.list")
                        .font(.largeTitle.weight(.semibold))
                        .foregroundStyle(.white)
                }
                .frame(width: 132, height: 132)
                .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))

                VStack(alignment: .leading, spacing: 6) {
                    Text(playlist.name)
                        .font(.title2.bold())
                        .lineLimit(2)
                    Text(playlist.trackCountText)
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    HStack(spacing: 10) {
                        Button {
                            if let first = playlist.orderedTracks.first {
                                app.play(first, queue: playlist.orderedTracks)
                            }
                        } label: {
                            Label("Play", systemImage: "play.fill")
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(playlist.orderedTracks.isEmpty)

                        Button {
                            let tracks = playlist.orderedTracks.shuffled()
                            if let first = tracks.first {
                                app.play(first, queue: tracks)
                            }
                        } label: {
                            Image(systemName: "shuffle")
                        }
                        .buttonStyle(.bordered)
                        .disabled(playlist.orderedTracks.isEmpty)

                        Button(role: .destructive) {
                            Task { await app.deletePlaylist(playlist) }
                        } label: {
                            Label("Delete", systemImage: "trash")
                        }
                        .buttonStyle(.bordered)
                    }
                    .padding(.top, 6)
                }
            }
            .padding(.horizontal)

            if playlist.orderedTracks.isEmpty {
                ContentUnavailableView("No tracks", systemImage: "music.note", description: Text("Add songs from a track menu."))
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity)
                    .padding(.top, 24)
            } else {
                LazyVStack(spacing: 10) {
                    ForEach(playlist.orderedTracks) { track in
                        TrackRowNative(track: track, playlist: playlist)
                            .environmentObject(app)
                    }
                }
                .padding(.horizontal)
            }
        }
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
    var playlist: PlaylistDetail? = nil

    var body: some View {
        ZStack(alignment: .leading) {
            Label("Queue", systemImage: "text.badge.plus")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.white)
                .padding(.horizontal, 14)
                .frame(maxHeight: .infinity)
                .opacity(dragOffset > 8 ? 1 : 0)

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

                if app.isTrackAvailableOffline(track) {
                    Image(systemName: "arrow.down.circle.fill")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.blue)
                }

                Text(track.durationText)
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)

                Menu {
                    Button {
                        app.addToQueue(track)
                    } label: {
                        Label("Add to Queue", systemImage: "text.badge.plus")
                    }
                    if !app.playlists.isEmpty {
                        Menu {
                            ForEach(app.playlists) { playlist in
                                Button {
                                    Task { await app.addTrack(track, to: playlist) }
                                } label: {
                                    Label(playlist.name, systemImage: "music.note.list")
                                }
                            }
                        } label: {
                            Label("Add to Playlist", systemImage: "text.badge.plus")
                        }
                    }
                    if let playlist {
                        Button(role: .destructive) {
                            Task { await app.removeTrack(track, from: playlist) }
                        } label: {
                            Label("Remove from Playlist", systemImage: "minus.circle")
                        }
                    }
                    if app.isTrackAvailableOffline(track) {
                        Label("Available Offline", systemImage: "arrow.down.circle.fill")
                        Button(role: .destructive) {
                            app.removeDownloadedTrack(track)
                        } label: {
                            Label("Remove Download", systemImage: "trash")
                        }
                    } else {
                        Button {
                            Task { await app.downloadTrack(track) }
                        } label: {
                            Label("Download Offline", systemImage: "arrow.down.circle")
                        }
                    }
                    Button {
                        Task { await app.toggleLike(track) }
                    } label: {
                        Label(app.likedTrackIds.contains(track.id) ? "Unlike" : "Like", systemImage: app.likedTrackIds.contains(track.id) ? "heart.slash" : "heart")
                    }
                } label: {
                    if app.downloadingTrackIds.contains(track.id) {
                        ProgressView()
                            .frame(width: 28, height: 28)
                    } else {
                        Image(systemName: "ellipsis")
                            .foregroundStyle(.secondary)
                            .frame(width: 28, height: 28)
                    }
                }
                .disabled(app.downloadingTrackIds.contains(track.id))
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
            if let playlist {
                app.play(track, queue: playlist.orderedTracks)
            } else {
                app.play(track)
            }
        }
        .simultaneousGesture(
                DragGesture(minimumDistance: 24)
                    .onChanged { value in
                    guard value.translation.width > 0,
                          abs(value.translation.width) > abs(value.translation.height) * 1.2 else { return }
                    dragOffset = min(value.translation.width, 96)
                }
                .onEnded { value in
                    let shouldAddToQueue = value.translation.width > 70
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
                    Text(title)
                        .font(.title2.bold())
                    Spacer()
                    if app.isSearchingTorrents { ProgressView() }
                }
                .padding(.horizontal)
                .padding(.top, 12)

                if app.searchText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    ContentUnavailableView(emptyTitle, systemImage: "magnifyingglass", description: Text("Type an artist, album, or song above."))
                        .foregroundStyle(.secondary)
                        .padding(.top, 48)
                } else if app.torrents.isEmpty && !app.isSearchingTorrents {
                    ContentUnavailableView("No results", systemImage: "tray", description: Text("Try a different query."))
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

    private var title: String {
        if app.searchMode == .indexer {
            return app.searchText.isEmpty ? "Indexer Search" : "Indexer Results"
        }
        return app.searchText.isEmpty ? "Torrent Search" : "Torrent Results"
    }

    private var emptyTitle: String {
        app.searchMode == .indexer ? "Search indexers" : "Search torrents"
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
    @State private var showingNowPlaying = false

    var body: some View {
        VStack(spacing: 10) {
            ScrubbablePlaybackBar(tint: .blue)
                .environmentObject(app)

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
                Button {
                    showingNowPlaying = true
                } label: {
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
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)

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
        .sheet(isPresented: $showingNowPlaying) {
            NowPlayingSheetView()
                .environmentObject(app)
                .presentationDetents([.large])
        }
    }
}

struct ScrubbablePlaybackBar: View {
    @EnvironmentObject private var app: AppState
    let tint: Color

    var body: some View {
        GeometryReader { proxy in
            ZStack(alignment: .leading) {
                Capsule()
                    .fill(Color.white.opacity(0.16))
                    .frame(height: 4)

                Capsule()
                    .fill(tint)
                    .frame(width: proxy.size.width * app.playbackProgress, height: 4)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { value in
                        seek(to: value.location.x, width: proxy.size.width)
                    }
                    .onEnded { value in
                        seek(to: value.location.x, width: proxy.size.width)
                    }
            )
        }
        .frame(height: 18)
        .accessibilityLabel("Playback position")
        .accessibilityValue("\(Int(app.playbackProgress * 100)) percent")
    }

    private func seek(to x: CGFloat, width: CGFloat) {
        guard width > 0,
              let duration = app.currentTrack?.durationSeconds,
              duration.isFinite,
              duration > 0 else { return }
        let fraction = min(max(Double(x / width), 0), 1)
        app.seek(to: duration * fraction)
    }
}

struct NowPlayingSheetView: View {
    @EnvironmentObject private var app: AppState
    @Environment(\.dismiss) private var dismiss
    @State private var showingQueue = false

    var body: some View {
        NavigationStack {
            ZStack {
                LinearGradient(
                    colors: [Color(red: 0.06, green: 0.08, blue: 0.13), Color(red: 0.01, green: 0.02, blue: 0.04)],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .ignoresSafeArea()

                if let track = app.currentTrack {
                    ScrollView {
                        VStack(spacing: 24) {
                            GeometryReader { proxy in
                                let size = min(proxy.size.width - 48, 340)
                                TrackArtworkView(track: track, size: size)
                                    .environmentObject(app)
                                    .shadow(color: .black.opacity(0.45), radius: 24, y: 16)
                                    .frame(maxWidth: .infinity)
                            }
                            .frame(height: 350)

                            VStack(alignment: .leading, spacing: 8) {
                                HStack(alignment: .top, spacing: 12) {
                                    VStack(alignment: .leading, spacing: 6) {
                                        Text(track.title)
                                            .font(.title2.bold())
                                            .foregroundStyle(.white)
                                            .lineLimit(2)
                                        Text(track.displayArtist)
                                            .font(.headline)
                                            .foregroundStyle(.secondary)
                                            .lineLimit(1)
                                        Text(track.displayAlbum)
                                            .font(.subheadline)
                                            .foregroundStyle(.secondary)
                                            .lineLimit(1)
                                    }

                                    Spacer()

                                    Button {
                                        Task { await app.toggleLike(track) }
                                    } label: {
                                        Image(systemName: app.likedTrackIds.contains(track.id) ? "heart.fill" : "heart")
                                            .font(.title3.weight(.semibold))
                                            .foregroundStyle(app.likedTrackIds.contains(track.id) ? .pink : .white)
                                    }
                                    .accessibilityLabel(app.likedTrackIds.contains(track.id) ? "Unlike" : "Like")
                                }

                                ScrubbablePlaybackBar(tint: .white)
                                    .environmentObject(app)
                                    .padding(.top, 12)

                                HStack {
                                    Text(progressText(for: track))
                                    Spacer()
                                    Text(track.durationText)
                                }
                                .font(.caption.monospacedDigit())
                                .foregroundStyle(.secondary)
                            }

                            HStack(spacing: 26) {
                                Button { app.toggleShuffle() } label: {
                                    Image(systemName: "shuffle")
                                        .foregroundStyle(app.shuffleEnabled ? .blue : .white)
                                }

                                Button { app.previousTrack() } label: {
                                    Image(systemName: "backward.fill")
                                }

                                Button { app.togglePlayback() } label: {
                                    Image(systemName: app.isPlaying ? "pause.fill" : "play.fill")
                                        .font(.title.weight(.bold))
                                        .frame(width: 68, height: 68)
                                        .background(Color.white)
                                        .foregroundStyle(Color.black)
                                        .clipShape(Circle())
                                }

                                Button { app.nextTrack() } label: {
                                    Image(systemName: "forward.fill")
                                }

                                Button { app.cycleRepeatMode() } label: {
                                    Image(systemName: app.repeatMode.iconName)
                                        .foregroundStyle(app.repeatMode.isActive ? .blue : .white)
                                }
                            }
                            .font(.title2.weight(.semibold))
                            .foregroundStyle(.white)

                            HStack(spacing: 12) {
                                if app.isTrackAvailableOffline(track) {
                                    Button(role: .destructive) {
                                        app.removeDownloadedTrack(track)
                                    } label: {
                                        Label("Remove", systemImage: "trash")
                                    }
                                } else {
                                    Button {
                                        Task { await app.downloadTrack(track) }
                                    } label: {
                                        if app.downloadingTrackIds.contains(track.id) {
                                            ProgressView()
                                        } else {
                                            Label("Download", systemImage: "arrow.down.circle")
                                        }
                                    }
                                    .disabled(app.downloadingTrackIds.contains(track.id))
                                }

                                Button {
                                    app.addToQueue(track)
                                } label: {
                                    Label("Queue", systemImage: "text.badge.plus")
                                }

                                Button {
                                    showingQueue = true
                                } label: {
                                    Label("Up Next", systemImage: "list.bullet")
                                }
                            }
                            .buttonStyle(.bordered)
                            .controlSize(.large)

                            VStack(alignment: .leading, spacing: 12) {
                                HStack {
                                    Text("Up Next")
                                        .font(.headline)
                                        .foregroundStyle(.white)
                                    Spacer()
                                    Button("Open") { showingQueue = true }
                                        .font(.subheadline.weight(.semibold))
                                }

                                if app.upcomingQueueTracks.isEmpty {
                                    Text("No upcoming tracks")
                                        .font(.subheadline)
                                        .foregroundStyle(.secondary)
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                        .padding(14)
                                        .background(Color.white.opacity(0.06))
                                        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                                } else {
                                    ForEach(app.upcomingQueueTracks.prefix(5)) { queuedTrack in
                                        QueueTrackRow(track: queuedTrack, isCurrent: false)
                                            .environmentObject(app)
                                            .padding(12)
                                            .background(Color.white.opacity(0.06))
                                            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                                    }
                                }
                            }
                        }
                        .padding(.horizontal, 22)
                        .padding(.top, 20)
                        .padding(.bottom, 32)
                    }
                } else {
                    ContentUnavailableView("Nothing playing", systemImage: "music.note", description: Text("Choose a song from your library."))
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Now Playing")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button { dismiss() } label: {
                        Image(systemName: "chevron.down")
                    }
                    .foregroundStyle(.white)
                }
            }
            .sheet(isPresented: $showingQueue) {
                QueueSheetView()
                    .environmentObject(app)
                    .presentationDetents([.medium, .large])
            }
        }
    }

    private func progressText(for track: ApiTrack) -> String {
        guard let duration = track.durationSeconds, duration.isFinite, duration > 0 else { return "0:00" }
        let elapsed = max(0, min(duration, duration * app.playbackProgress))
        let total = Int(elapsed.rounded())
        return "\(total / 60):\(String(format: "%02d", total % 60))"
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
                    Label {
                        Text(app.isTestingConnection ? "Testing connection..." : "Test connection")
                    } icon: {
                        if app.isTestingConnection {
                            ProgressView()
                        } else {
                            Image(systemName: "network")
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .center)
                }
                .buttonStyle(.borderedProminent)
                .disabled(app.isTestingConnection)

                Button {
                    Task { await app.refreshLibrary() }
                } label: {
                    Label {
                        Text(app.isLoading ? "Refreshing library..." : "Refresh library")
                    } icon: {
                        if app.isLoading {
                            ProgressView()
                        } else {
                            Image(systemName: "arrow.clockwise")
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .center)
                }
                .buttonStyle(.bordered)
                .disabled(app.isLoading)
            }

            Section("Detected endpoint") {
                Text(app.normalizedEndpoint.isEmpty ? "Not set" : app.normalizedEndpoint)
                    .font(.footnote.monospaced())
                    .textSelection(.enabled)
            }

            Section("Indexers") {
                SecureField("Prowlarr API key", text: $app.prowlarrApiKey)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()

                Text(app.prowlarrApiKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "Using backend .env key" : "Using this device key")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }

            Section("Playback") {
                Toggle(isOn: $app.autoplaySimilarEnabled) {
                    Label("Autoplay Similar Songs", systemImage: "infinity")
                }
            }

            Section("Offline Downloads") {
                Label("\(app.offlineTrackCount) downloaded songs", systemImage: "arrow.down.circle.fill")
                Text(app.offlineStorageText)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                if let message = app.offlineStatusMessage {
                    Text(message)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                Button(role: .destructive) {
                    app.removeAllDownloads()
                } label: {
                    Label("Remove All Downloads", systemImage: "trash")
                }
                .disabled(app.offlineTrackCount == 0)
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
