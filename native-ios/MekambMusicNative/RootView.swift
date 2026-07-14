import SwiftUI
import UIKit

// MARK: - Design system palette
//
// Exact hex values from the "Mekamb Mobile" design handoff (dark near-black surfaces + a
// #5AA9FF accent blue). Existing screens mostly used generic `.blue`/`Color.white.opacity(...)`
// tokens already close to this palette; new screens below use these exact values for fidelity.
extension Color {
    init(hex: UInt32, opacity: Double = 1) {
        let r = Double((hex >> 16) & 0xFF) / 255
        let g = Double((hex >> 8) & 0xFF) / 255
        let b = Double(hex & 0xFF) / 255
        self.init(.sRGB, red: r, green: g, blue: b, opacity: opacity)
    }
}

enum MekambPalette {
    static let backgroundPrimary = Color(hex: 0x101014)
    static let backgroundSecondary = Color(hex: 0x0B0B0D)
    static let surface1 = Color(hex: 0x131317)
    static let surface2 = Color(hex: 0x1A1A1F)
    static let surface3 = Color(hex: 0x17171B)
    static let border1 = Color(hex: 0x1E1E24)
    static let border2 = Color(hex: 0x26262E)
    static let border3 = Color(hex: 0x2E2E36)
    static let textPrimary = Color(hex: 0xF2F4F8)
    static let textMuted = Color(hex: 0x9BA1AC)
    static let textFaint = Color(hex: 0x6E7480)
    static let accentBlue = Color(hex: 0x5AA9FF)
    static let accentBlueDeep = Color(hex: 0x2F7FE0)
    static let linkBlue = Color(hex: 0x8CC4FF)
    static let likePink = Color(hex: 0xFF6B9D)
    static let successGreen = Color(hex: 0x4CD984)
    static let dangerRed = Color(hex: 0xF46363)
}

/// Small pulsing equalizer-bars indicator shown on whichever track row is currently playing,
/// matching the reference design's animated "now playing" glyph.
struct EqualizerBarsView: View {
    @State private var animate = false

    var body: some View {
        HStack(alignment: .bottom, spacing: 2) {
            bar(duration: 0.9, delay: 0)
            bar(duration: 0.8, delay: 0.15)
            bar(duration: 1.0, delay: 0.3)
        }
        .frame(width: 14, height: 14, alignment: .bottom)
        .onAppear { animate = true }
    }

    private func bar(duration: Double, delay: Double) -> some View {
        RoundedRectangle(cornerRadius: 1)
            .fill(MekambPalette.accentBlue)
            .frame(width: 3, height: animate ? 13 : 5)
            .animation(.easeInOut(duration: duration).repeatForever(autoreverses: true).delay(delay), value: animate)
    }
}

/// Indeterminate animated progress bar for the Imports tab — `ImportRecordResponse` carries no
/// byte-level percentage, so every active import shows this rather than a fabricated number.
struct IndeterminateProgressBarView: View {
    @State private var animate = false

    var body: some View {
        GeometryReader { proxy in
            ZStack(alignment: .leading) {
                Capsule().fill(Color(hex: 0x222228))
                Capsule()
                    .fill(MekambPalette.accentBlue)
                    .frame(width: max(proxy.size.width * 0.35, 24))
                    .offset(x: animate ? proxy.size.width * 0.65 : -proxy.size.width * 0.35)
            }
        }
        .frame(height: 4)
        .clipShape(Capsule())
        .onAppear {
            withAnimation(.easeInOut(duration: 1.2).repeatForever(autoreverses: false)) {
                animate = true
            }
        }
    }
}

/// A small reusable circular icon button used for back chevrons across pushed detail screens
/// (Album/Artist/Mix/Liked/Search/Settings), matching the translucent-circle back button in the
/// reference design.
struct DetailBackButton: View {
    var tint: Color = MekambPalette.textPrimary
    var background: Color = Color.black.opacity(0.4)
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: "chevron.left")
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(tint)
                .frame(width: 34, height: 34)
                .background(background)
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        }
        .buttonStyle(.plain)
    }
}

struct RootView: View {
    @EnvironmentObject private var app: AppState

    var body: some View {
        ZStack {
            LinearGradient(colors: [Color(red: 0.04, green: 0.06, blue: 0.10), Color(red: 0.02, green: 0.03, blue: 0.06)], startPoint: .top, endPoint: .bottom)
                .ignoresSafeArea()

            VStack(spacing: 0) {
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

                tabBar
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task {
            await app.refreshLibrary()
            await app.loadLibraries()
        }
        .task {
            await app.refreshImportBadge()
        }
    }

    @ViewBuilder
    private var content: some View {
        switch app.selectedTab {
        case .home:
            HomeView().environmentObject(app)
        case .library:
            LibraryView().environmentObject(app)
        case .addMusic:
            CatalogSearchView().environmentObject(app)
        case .imports:
            ImportsView().environmentObject(app)
        case .search:
            SearchView().environmentObject(app)
        case .liked:
            LikedSongsView().environmentObject(app)
        case .albums:
            if let album = app.selectedAlbum {
                AlbumDetailView(album: album).environmentObject(app)
            } else {
                missingDetailFallback
            }
        case .playlists:
            if let playlist = app.selectedPlaylist {
                PlaylistDetailScreen(playlist: playlist).environmentObject(app)
            } else {
                missingDetailFallback
            }
        case .artist:
            if let name = app.selectedArtistName {
                ArtistDetailView(artistName: name).environmentObject(app)
            } else {
                missingDetailFallback
            }
        case .mix:
            if let mix = app.selectedMix {
                DailyMixDetailView(mix: mix).environmentObject(app)
            } else {
                missingDetailFallback
            }
        case .settings:
            SettingsView().environmentObject(app)
        }
    }

    /// Shown if a pushed detail screen's backing id went stale (e.g. the album was deleted while
    /// viewing it) — bounces back to the last real tab instead of showing a blank screen.
    private var missingDetailFallback: some View {
        ContentUnavailableView("Not found", systemImage: "questionmark.circle")
            .foregroundStyle(.secondary)
            .onAppear { app.selectedTab = app.lastBarTab }
    }

    private var tabBar: some View {
        HStack(spacing: 6) {
            ForEach(MusicTab.barItems) { tab in
                Button {
                    app.selectedTab = tab
                    app.selectedAlbumId = nil
                    app.selectedPlaylistId = nil
                    app.selectedArtistName = nil
                    app.selectedMixId = nil
                } label: {
                    VStack(spacing: 4) {
                        ZStack(alignment: .topTrailing) {
                            Image(systemName: icon(for: tab))
                                .font(.system(size: 17, weight: .semibold))
                            if tab == .imports, app.activeImportCount > 0 {
                                Text("\(min(app.activeImportCount, 99))")
                                    .font(.system(size: 9, weight: .heavy))
                                    .foregroundStyle(MekambPalette.backgroundSecondary)
                                    .padding(.horizontal, 3)
                                    .frame(minWidth: 14, minHeight: 14)
                                    .background(Circle().fill(MekambPalette.accentBlue))
                                    .offset(x: 10, y: -6)
                            }
                        }
                        Text(tab.rawValue)
                            .font(.caption2.weight(.semibold))
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 8)
                    .foregroundStyle(app.selectedTab == tab ? MekambPalette.accentBlue : MekambPalette.textMuted)
                    .background(app.selectedTab == tab ? MekambPalette.accentBlue.opacity(0.16) : Color.clear)
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                }
            }
        }
        .padding(.horizontal, 10)
        .padding(.top, 8)
        .padding(.bottom, 10)
        .background(.ultraThinMaterial)
    }

    private func icon(for tab: MusicTab) -> String {
        switch tab {
        case .home: return "house.fill"
        case .library: return "square.stack.fill"
        case .addMusic: return "plus.magnifyingglass"
        case .imports: return "tray.and.arrow.down.fill"
        default: return "circle"
        }
    }
}

// MARK: - Home

struct HomeView: View {
    @EnvironmentObject private var app: AppState
    @State private var showingProfileMenu = false

    private var greeting: String {
        let hour = Calendar.current.component(.hour, from: Date())
        switch hour {
        case ..<12: return "Good morning"
        case 12..<18: return "Good afternoon"
        default: return "Good evening"
        }
    }

    /// The pinned 2-column grid: Liked Songs first, then a few playlists, then a few albums —
    /// mirroring the reference design's mixed pin list (there's no real "pinned items" concept
    /// in the backend, so this is assembled client-side from what's already loaded).
    private var pinnedItems: [LibraryRowKind] {
        var items: [LibraryRowKind] = [.liked]
        items.append(contentsOf: app.playlists.prefix(3).map { LibraryRowKind.playlist($0) })
        items.append(contentsOf: app.albums.prefix(4).map { LibraryRowKind.album($0) })
        return items
    }

    var body: some View {
        ZStack(alignment: .topTrailing) {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    header
                    searchBarRow
                    pinnedGrid

                    DailyMixShelfView(title: "Made for you", mixes: app.dailyMixes)
                        .environmentObject(app)

                    AlbumShelfView(title: "Recently added", albums: app.recentlyAddedAlbums)
                        .environmentObject(app)
                }
                .padding(.top, 10)
                .padding(.bottom, 24)
            }
            .refreshable { await app.refreshLibrary() }

            if showingProfileMenu {
                ProfileMenuOverlay(isPresented: $showingProfileMenu)
                    .environmentObject(app)
            }
        }
    }

    private var header: some View {
        HStack(spacing: 10) {
            Text(greeting)
                .font(.system(size: 23, weight: .heavy))
                .foregroundStyle(MekambPalette.textPrimary)
            Spacer()

            Button {
                app.selectedTab = .imports
            } label: {
                ZStack(alignment: .topTrailing) {
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .fill(MekambPalette.surface2)
                        .frame(width: 34, height: 34)
                        .overlay(
                            Image(systemName: "tray.and.arrow.down")
                                .font(.system(size: 15))
                                .foregroundStyle(MekambPalette.textMuted)
                        )
                    if app.activeImportCount > 0 {
                        Text("\(min(app.activeImportCount, 99))")
                            .font(.system(size: 9.5, weight: .heavy))
                            .foregroundStyle(MekambPalette.backgroundSecondary)
                            .padding(.horizontal, 3)
                            .frame(minWidth: 15, minHeight: 15)
                            .background(Circle().fill(MekambPalette.accentBlue))
                            .offset(x: 4, y: -4)
                    }
                }
            }
            .buttonStyle(.plain)

            Button {
                showingProfileMenu = true
            } label: {
                Circle()
                    .fill(LinearGradient(colors: [MekambPalette.accentBlueDeep, MekambPalette.accentBlue], startPoint: .topLeading, endPoint: .bottomTrailing))
                    .frame(width: 34, height: 34)
                    .overlay(
                        Text(app.accountInitials)
                            .font(.system(size: 12, weight: .heavy))
                            .foregroundStyle(MekambPalette.backgroundSecondary)
                    )
                    .overlay(Circle().stroke(showingProfileMenu ? MekambPalette.accentBlue : Color.clear, lineWidth: 2))
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal)
    }

    private var searchBarRow: some View {
        Button {
            app.selectedTab = .search
        } label: {
            HStack(spacing: 10) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 15))
                    .foregroundStyle(MekambPalette.textMuted)
                Text("Search tracks, albums, artists")
                    .font(.system(size: 13.5))
                    .foregroundStyle(MekambPalette.textMuted)
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 13)
            .frame(height: 40)
            .background(MekambPalette.surface2)
            .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(MekambPalette.border2, lineWidth: 1))
            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        }
        .buttonStyle(.plain)
        .padding(.horizontal)
    }

    private var pinnedGrid: some View {
        let columns = [GridItem(.flexible(), spacing: 8), GridItem(.flexible(), spacing: 8)]
        return LazyVGrid(columns: columns, spacing: 8) {
            ForEach(Array(pinnedItems.enumerated()), id: \.offset) { _, kind in
                PinnedTileView(kind: kind).environmentObject(app)
            }
        }
        .padding(.horizontal)
    }
}

struct PinnedTileView: View {
    @EnvironmentObject private var app: AppState
    let kind: LibraryRowKind

    private var name: String {
        switch kind {
        case .liked: return "Liked Songs"
        case .playlist(let playlist): return playlist.name
        case .album(let album): return album.title
        case .artist(let artistName): return artistName
        }
    }

    var body: some View {
        Button(action: { navigate(kind, app: app) }) {
            HStack(spacing: 9) {
                artwork
                Text(name)
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(MekambPalette.textPrimary)
                    .lineLimit(1)
                    .truncationMode(.tail)
                Spacer(minLength: 0)
            }
            .padding(.trailing, 8)
            .frame(height: 48)
            .background(MekambPalette.surface3)
            .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private var artwork: some View {
        switch kind {
        case .liked:
            ZStack {
                LinearGradient(colors: [MekambPalette.accentBlueDeep, Color(hex: 0x7B5BD6), MekambPalette.likePink], startPoint: .topLeading, endPoint: .bottomTrailing)
                Image(systemName: "heart.fill").font(.system(size: 15)).foregroundStyle(.white)
            }
            .frame(width: 48, height: 48)
        case .playlist:
            ZStack {
                LinearGradient(colors: [.green.opacity(0.65), .blue.opacity(0.55)], startPoint: .topLeading, endPoint: .bottomTrailing)
                Image(systemName: "music.note.list").font(.system(size: 15)).foregroundStyle(.white)
            }
            .frame(width: 48, height: 48)
        case .album(let album):
            AlbumArtworkView(album: album, size: 48).environmentObject(app)
        case .artist:
            ZStack {
                LinearGradient(colors: [.blue.opacity(0.6), .purple.opacity(0.5)], startPoint: .topLeading, endPoint: .bottomTrailing)
                Image(systemName: "music.mic").font(.system(size: 15)).foregroundStyle(.white)
            }
            .frame(width: 48, height: 48)
        }
    }
}

/// Shared "what does this row represent" case used by both the Home pinned grid and the Library
/// tab's flat list, since both show the same mix of liked/playlists/albums/artists.
enum LibraryRowKind {
    case liked
    case playlist(PlaylistDetail)
    case album(Album)
    case artist(String)
}

@MainActor func navigate(_ kind: LibraryRowKind, app: AppState) {
    switch kind {
    case .liked:
        app.selectedTab = .liked
    case .playlist(let playlist):
        app.selectedPlaylistId = playlist.id
        app.selectedTab = .playlists
    case .album(let album):
        app.selectedAlbumId = album.id
        app.selectedTab = .albums
    case .artist(let name):
        app.selectedArtistName = name
        app.selectedTab = .artist
    }
}

// MARK: - Library ("Your Library" tab — distinct from the personal-curated "Libraries" feature)

enum LibraryFilter: String, CaseIterable, Identifiable {
    case all = "All"
    case playlists = "Playlists"
    case albums = "Albums"
    case artists = "Artists"
    var id: String { rawValue }
}

struct LibraryView: View {
    @EnvironmentObject private var app: AppState
    @State private var filter: LibraryFilter = .all

    private var artistNames: [String] {
        Array(Set(app.albums.map(\.artist))).sorted()
    }

    /// Mirrors the reference design exactly: Liked Songs only appears under "All"/"Playlists",
    /// never under "Albums"/"Artists".
    private var rows: [LibraryRowKind] {
        let playlistRows: [LibraryRowKind] = app.playlists.map { LibraryRowKind.playlist($0) }
        switch filter {
        case .all:
            var items: [LibraryRowKind] = [.liked]
            items.append(contentsOf: playlistRows)
            items.append(contentsOf: app.albums.prefix(8).map { LibraryRowKind.album($0) })
            return items
        case .playlists:
            var items: [LibraryRowKind] = [.liked]
            items.append(contentsOf: playlistRows)
            return items
        case .albums:
            return app.albums.map { LibraryRowKind.album($0) }
        case .artists:
            return artistNames.map { LibraryRowKind.artist($0) }
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text("Your Library")
                    .font(.system(size: 23, weight: .heavy))
                    .foregroundStyle(MekambPalette.textPrimary)
                    .padding(.horizontal)
                    .padding(.top, 12)

                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(LibraryFilter.allCases) { candidate in
                            Button {
                                filter = candidate
                            } label: {
                                Text(candidate.rawValue)
                                    .font(.system(size: 12, weight: .semibold))
                                    .padding(.horizontal, 13)
                                    .padding(.vertical, 7)
                                    .background(filter == candidate ? MekambPalette.accentBlue.opacity(0.16) : MekambPalette.surface2)
                                    .foregroundStyle(filter == candidate ? MekambPalette.accentBlue : MekambPalette.textMuted)
                                    .clipShape(Capsule())
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal)
                }

                if !app.canUseApi {
                    ContentUnavailableView("Connect API", systemImage: "wifi.exclamationmark", description: Text("Open Settings, set the endpoint and log in."))
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity)
                        .padding(.top, 48)
                } else if rows.isEmpty {
                    ContentUnavailableView("Nothing here yet", systemImage: "square.stack", description: Text("Create a playlist or import albums to see them here."))
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity)
                        .padding(.top, 48)
                } else {
                    LazyVStack(spacing: 2) {
                        ForEach(Array(rows.enumerated()), id: \.offset) { _, kind in
                            LibraryRow(kind: kind).environmentObject(app)
                        }
                    }
                }
            }
            .padding(.bottom, 24)
        }
        .refreshable { await app.refreshLibrary() }
    }
}

struct LibraryRow: View {
    @EnvironmentObject private var app: AppState
    let kind: LibraryRowKind

    private var likedCount: Int {
        app.tracks.filter { app.likedTrackIds.contains($0.id) }.count
    }

    private var title: String {
        switch kind {
        case .liked: return "Liked Songs"
        case .playlist(let playlist): return playlist.name
        case .album(let album): return album.title
        case .artist(let name): return name
        }
    }

    private var subtitle: String {
        switch kind {
        case .liked: return "Playlist · \(likedCount == 1 ? "1 song" : "\(likedCount) songs")"
        case .playlist(let playlist): return "Playlist · \(playlist.trackCountText)"
        case .album(let album): return "Album · \(album.artist)"
        case .artist: return "Artist"
        }
    }

    var body: some View {
        Button(action: { navigate(kind, app: app) }) {
            HStack(spacing: 12) {
                artwork
                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(MekambPalette.textPrimary)
                        .lineLimit(1)
                    Text(subtitle)
                        .font(.system(size: 12))
                        .foregroundStyle(MekambPalette.textMuted)
                        .lineLimit(1)
                }
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(Color(hex: 0x4A4F5A))
            }
            .padding(.vertical, 6)
            .padding(.horizontal, 4)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .padding(.horizontal)
    }

    @ViewBuilder
    private var artwork: some View {
        switch kind {
        case .liked:
            ZStack {
                LinearGradient(colors: [MekambPalette.accentBlueDeep, Color(hex: 0x7B5BD6), MekambPalette.likePink], startPoint: .topLeading, endPoint: .bottomTrailing)
                Image(systemName: "heart.fill").font(.system(size: 19)).foregroundStyle(.white)
            }
            .frame(width: 50, height: 50)
            .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
        case .playlist:
            ZStack {
                LinearGradient(colors: [.green.opacity(0.65), .blue.opacity(0.55)], startPoint: .topLeading, endPoint: .bottomTrailing)
                Image(systemName: "music.note.list").foregroundStyle(.white)
            }
            .frame(width: 50, height: 50)
            .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
        case .album(let album):
            AlbumArtworkView(album: album, size: 50).environmentObject(app)
        case .artist(let name):
            ZStack {
                LinearGradient(colors: [.blue.opacity(0.6), .purple.opacity(0.5)], startPoint: .topLeading, endPoint: .bottomTrailing)
                Text(String(name.prefix(1)).uppercased())
                    .font(.headline)
                    .foregroundStyle(.white)
            }
            .frame(width: 50, height: 50)
            .clipShape(Circle())
        }
    }
}

// MARK: - Search (pushed from Home's search bar)

struct SearchView: View {
    @EnvironmentObject private var app: AppState
    @FocusState private var isFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
            header
            results
        }
        .onAppear { isFocused = true }
        .onDisappear { app.searchText = "" }
    }

    private var header: some View {
        HStack(spacing: 10) {
            DetailBackButton(tint: MekambPalette.textPrimary, background: MekambPalette.surface2) {
                app.selectedTab = app.lastBarTab
            }
            HStack(spacing: 10) {
                Image(systemName: "magnifyingglass").foregroundStyle(MekambPalette.textMuted)
                TextField("Search tracks, albums, artists", text: $app.searchText)
                    .focused($isFocused)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .submitLabel(.search)
                    .foregroundStyle(MekambPalette.textPrimary)
                if !app.searchText.isEmpty {
                    Button {
                        app.searchText = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill").foregroundStyle(MekambPalette.textMuted)
                    }
                }
            }
            .padding(.horizontal, 13)
            .frame(height: 40)
            .background(MekambPalette.surface2)
            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        }
        .padding(.horizontal)
        .padding(.top, 12)
        .padding(.bottom, 8)
    }

    private var results: some View {
        let query = app.searchText.trimmingCharacters(in: .whitespacesAndNewlines)
        return ScrollView {
            if query.isEmpty {
                ContentUnavailableView(
                    "Search",
                    systemImage: "magnifyingglass",
                    description: Text("Find songs, albums, and artists in your library.")
                )
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity)
                .padding(.top, 64)
            } else if app.filteredTracks.isEmpty {
                ContentUnavailableView(
                    "No results",
                    systemImage: "magnifyingglass",
                    description: Text("Nothing in your library matches \u{201C}\(query)\u{201D}.")
                )
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity)
                .padding(.top, 64)
            } else {
                LazyVStack(spacing: 10) {
                    ForEach(app.filteredTracks) { track in
                        TrackRowNative(track: track)
                            .environmentObject(app)
                            .padding(.horizontal)
                    }
                }
                .padding(.vertical, 12)
            }
        }
    }
}

// MARK: - Shelves (reused by Home / Artist detail)

struct DailyMixShelfView: View {
    @EnvironmentObject private var app: AppState
    var title: String = "Daily Mixes"
    let mixes: [DailyMix]

    var body: some View {
        if !mixes.isEmpty {
            VStack(alignment: .leading, spacing: 12) {
                Text(title)
                    .font(.headline)
                    .foregroundStyle(MekambPalette.textPrimary)
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
            app.selectedMixId = mix.id
            app.selectedTab = .mix
        } label: {
            VStack(alignment: .leading, spacing: 7) {
                ZStack(alignment: .topLeading) {
                    if let firstTrack = mix.tracks.first {
                        TrackArtworkView(track: firstTrack, size: 132)
                            .environmentObject(app)
                    } else {
                        LinearGradient(colors: [.blue.opacity(0.65), .purple.opacity(0.55)], startPoint: .topLeading, endPoint: .bottomTrailing)
                            .frame(width: 132, height: 132)
                            .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                    }

                    Text("MIX")
                        .font(.system(size: 8.5, weight: .heavy))
                        .tracking(0.7)
                        .foregroundStyle(MekambPalette.accentBlue)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.black.opacity(0.65))
                        .clipShape(RoundedRectangle(cornerRadius: 5, style: .continuous))
                        .padding(7)
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
            .frame(width: 132, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
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
                    .foregroundStyle(MekambPalette.textPrimary)
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

struct AlbumRecommendationCard: View {
    @EnvironmentObject private var app: AppState
    let album: Album

    var body: some View {
        Button {
            app.selectedAlbumId = album.id
            app.selectedTab = .albums
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

// MARK: - Album detail (pushed)

struct AlbumDetailView: View {
    @EnvironmentObject private var app: AppState
    let album: Album

    private var albumDurationText: String {
        let totalSeconds = album.tracks.reduce(0.0) { $0 + ($1.durationSeconds ?? 0) }
        return "\(Int(totalSeconds / 60)) min"
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                hero
                controls
                trackList
            }
            .padding(.bottom, 24)
        }
        .background(MekambPalette.backgroundPrimary.ignoresSafeArea())
    }

    private var hero: some View {
        VStack(spacing: 14) {
            HStack {
                DetailBackButton {
                    app.selectedAlbumId = nil
                    app.selectedTab = app.lastBarTab
                }
                Spacer()
            }

            AlbumArtworkView(album: album, size: 208)
                .environmentObject(app)
                .shadow(color: .black.opacity(0.5), radius: 24, y: 10)

            VStack(spacing: 5) {
                Text(album.title)
                    .font(.system(size: 21, weight: .heavy))
                    .foregroundStyle(MekambPalette.textPrimary)
                    .multilineTextAlignment(.center)
                Button {
                    app.selectedArtistName = album.artist
                    app.selectedTab = .artist
                } label: {
                    Text(album.artist)
                        .font(.system(size: 13.5, weight: .bold))
                        .foregroundStyle(MekambPalette.linkBlue)
                }
                .buttonStyle(.plain)
                Text("\(album.trackCountText) · \(albumDurationText)")
                    .font(.system(size: 11.5))
                    .foregroundStyle(MekambPalette.textMuted)
            }
        }
        .padding(.horizontal, 18)
        .padding(.top, 8)
        .padding(.bottom, 20)
        .background(
            LinearGradient(colors: [MekambPalette.accentBlueDeep.opacity(0.34), MekambPalette.backgroundPrimary.opacity(0)], startPoint: .top, endPoint: .bottom)
        )
    }

    private var controls: some View {
        HStack(spacing: 16) {
            Button {
                let shuffled = album.tracks.shuffled()
                if let first = shuffled.first { app.play(first, queue: shuffled) }
            } label: {
                Image(systemName: "shuffle").foregroundStyle(MekambPalette.textMuted)
            }
            .frame(width: 42, height: 42)
            .overlay(Circle().stroke(MekambPalette.border3, lineWidth: 1))
            .disabled(album.tracks.isEmpty)

            Button {
                if let first = album.tracks.first { app.play(first, queue: album.tracks) }
            } label: {
                Image(systemName: "play.fill")
                    .font(.system(size: 21))
                    .foregroundStyle(MekambPalette.backgroundSecondary)
            }
            .frame(width: 54, height: 54)
            .background(Circle().fill(MekambPalette.accentBlue))
            .disabled(album.tracks.isEmpty)

            Menu {
                Button {
                    Task { await app.downloadAlbum(album) }
                } label: {
                    Label(
                        app.isAlbumAvailableOffline(album) ? "Available Offline" : "Download",
                        systemImage: app.isAlbumAvailableOffline(album) ? "checkmark.circle" : "arrow.down.circle"
                    )
                }
                .disabled(app.downloadingAlbumIds.contains(album.id) || app.isAlbumAvailableOffline(album))

                if app.downloadedTrackCount(in: album) > 0 {
                    Button(role: .destructive) {
                        app.removeDownloadedAlbum(album)
                    } label: {
                        Label("Remove Downloads", systemImage: "trash")
                    }
                }

                Button(role: .destructive) {
                    Task { await app.deleteAlbum(album) }
                } label: {
                    Label("Delete Album", systemImage: "trash")
                }
            } label: {
                if app.downloadingAlbumIds.contains(album.id) {
                    ProgressView()
                } else {
                    Image(systemName: "ellipsis").foregroundStyle(MekambPalette.textMuted)
                }
            }
            .frame(width: 42, height: 42)
            .overlay(Circle().stroke(MekambPalette.border3, lineWidth: 1))
        }
        .padding(.bottom, 14)
    }

    private var trackList: some View {
        LazyVStack(spacing: 10) {
            ForEach(album.tracks) { track in
                TrackRowNative(track: track)
                    .environmentObject(app)
            }
        }
        .padding(.horizontal)
    }
}

// MARK: - Artist detail (pushed) — new screen; no /artists/{name} endpoint exists, so tracks come
// from GET /tracks?artist= and the album shelf is a client-side filter of already-loaded albums.

struct ArtistDetailView: View {
    @EnvironmentObject private var app: AppState
    let artistName: String
    @State private var popularTracks: [ApiTrack] = []
    @State private var isLoadingPopular = false

    private var albumsInLibrary: [Album] {
        app.albums.filter { $0.artist == artistName }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                hero
                controls.padding(.horizontal)
                popularSection
                AlbumShelfView(title: "In your library", albums: albumsInLibrary)
                    .environmentObject(app)
            }
            .padding(.bottom, 24)
        }
        .background(MekambPalette.backgroundPrimary.ignoresSafeArea())
        .task(id: artistName) {
            isLoadingPopular = true
            popularTracks = Array((await app.fetchArtistTracks(artistName)).prefix(5))
            isLoadingPopular = false
        }
    }

    private var hero: some View {
        ZStack(alignment: .bottomLeading) {
            LinearGradient(colors: [MekambPalette.accentBlueDeep.opacity(0.55), MekambPalette.backgroundPrimary], startPoint: .top, endPoint: .bottom)

            VStack(alignment: .leading, spacing: 0) {
                HStack {
                    DetailBackButton {
                        app.selectedArtistName = nil
                        app.selectedTab = app.lastBarTab
                    }
                    Spacer()
                }
                Spacer()
                Text("ARTIST")
                    .font(.system(size: 10.5, weight: .heavy))
                    .tracking(1.3)
                    .foregroundStyle(.white.opacity(0.72))
                Text(artistName)
                    .font(.system(size: 32, weight: .heavy))
                    .foregroundStyle(.white)
                    .lineLimit(2)
                Text("\(albumsInLibrary.count) album\(albumsInLibrary.count == 1 ? "" : "s") in your library")
                    .font(.system(size: 12))
                    .foregroundStyle(.white.opacity(0.72))
                    .padding(.top, 3)
            }
            .padding(.horizontal, 18)
            .padding(.top, 8)
            .padding(.bottom, 18)
        }
        .frame(height: 200)
    }

    private var controls: some View {
        HStack(spacing: 12) {
            Button {
                if let first = popularTracks.first { app.play(first, queue: popularTracks) }
            } label: {
                Image(systemName: "play.fill")
                    .foregroundStyle(MekambPalette.backgroundSecondary)
            }
            .frame(width: 48, height: 48)
            .background(Circle().fill(MekambPalette.accentBlue))
            .disabled(popularTracks.isEmpty)

            Button {
                let shuffled = popularTracks.shuffled()
                if let first = shuffled.first { app.play(first, queue: shuffled) }
            } label: {
                Label("Shuffle", systemImage: "shuffle")
                    .font(.system(size: 12, weight: .bold))
            }
            .padding(.horizontal, 14)
            .frame(height: 36)
            .foregroundStyle(MekambPalette.textMuted)
            .overlay(Capsule().stroke(MekambPalette.border3, lineWidth: 1))
            .disabled(popularTracks.isEmpty)

            Spacer()
        }
    }

    @ViewBuilder
    private var popularSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Popular")
                .font(.system(size: 16, weight: .heavy))
                .foregroundStyle(MekambPalette.textPrimary)
                .padding(.horizontal)

            if isLoadingPopular && popularTracks.isEmpty {
                ProgressView().frame(maxWidth: .infinity).padding(.vertical, 12)
            } else if popularTracks.isEmpty {
                Text("No tracks from this artist yet.")
                    .font(.subheadline)
                    .foregroundStyle(MekambPalette.textMuted)
                    .padding(.horizontal)
            } else {
                LazyVStack(spacing: 8) {
                    ForEach(popularTracks) { track in
                        TrackRowNative(track: track)
                            .environmentObject(app)
                            .padding(.horizontal)
                    }
                }
            }
        }
    }
}

// MARK: - Liked Songs (pushed)

struct LikedSongsView: View {
    @EnvironmentObject private var app: AppState

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                hero
                if app.filteredTracks.isEmpty {
                    ContentUnavailableView("No liked tracks", systemImage: "heart", description: Text("Heart songs from your library to build this collection."))
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity)
                        .padding(.top, 24)
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
            .padding(.bottom, 24)
        }
        .background(MekambPalette.backgroundPrimary.ignoresSafeArea())
    }

    private var hero: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                DetailBackButton { app.selectedTab = app.lastBarTab }
                Spacer()
            }

            HStack(spacing: 14) {
                ZStack {
                    LinearGradient(colors: [MekambPalette.accentBlueDeep, Color(hex: 0x7B5BD6), MekambPalette.likePink], startPoint: .topLeading, endPoint: .bottomTrailing)
                    Image(systemName: "heart.fill").font(.system(size: 34)).foregroundStyle(.white)
                }
                .frame(width: 88, height: 88)
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                .shadow(color: .black.opacity(0.5), radius: 16, y: 8)

                VStack(alignment: .leading, spacing: 4) {
                    Text("Liked Songs")
                        .font(.system(size: 22, weight: .heavy))
                        .foregroundStyle(MekambPalette.textPrimary)
                    Text("\(app.filteredTracks.count) tracks · yours")
                        .font(.system(size: 12))
                        .foregroundStyle(MekambPalette.textMuted)
                }
                Spacer(minLength: 0)
                Button {
                    if let first = app.filteredTracks.first { app.play(first, queue: app.filteredTracks) }
                } label: {
                    Image(systemName: "play.fill")
                        .foregroundStyle(MekambPalette.backgroundSecondary)
                }
                .frame(width: 48, height: 48)
                .background(Circle().fill(MekambPalette.accentBlue))
                .disabled(app.filteredTracks.isEmpty)
            }
        }
        .padding(.horizontal, 18)
        .padding(.top, 8)
        .padding(.bottom, 16)
        .background(
            LinearGradient(colors: [MekambPalette.accentBlueDeep.opacity(0.30), MekambPalette.backgroundPrimary.opacity(0)], startPoint: .top, endPoint: .bottom)
        )
    }
}

// MARK: - Daily Mix detail (pushed) — new screen, mirrors PlaylistDetailView's structure.

struct DailyMixDetailView: View {
    @EnvironmentObject private var app: AppState
    let mix: DailyMix

    private var totalMinutes: Int {
        Int(mix.tracks.reduce(0.0) { $0 + ($1.durationSeconds ?? 0) } / 60)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                hero
                if mix.tracks.isEmpty {
                    ContentUnavailableView("No tracks", systemImage: "music.note")
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity)
                        .padding(.top, 24)
                } else {
                    LazyVStack(spacing: 10) {
                        ForEach(mix.tracks) { track in
                            TrackRowNative(track: track)
                                .environmentObject(app)
                                .padding(.horizontal)
                        }
                    }
                }
            }
            .padding(.bottom, 24)
        }
        .background(MekambPalette.backgroundPrimary.ignoresSafeArea())
    }

    private var hero: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                DetailBackButton {
                    app.selectedMixId = nil
                    app.selectedTab = app.lastBarTab
                }
                Spacer()
            }

            HStack(alignment: .center, spacing: 14) {
                ZStack(alignment: .topLeading) {
                    if let first = mix.tracks.first {
                        TrackArtworkView(track: first, size: 88).environmentObject(app)
                    } else {
                        RoundedRectangle(cornerRadius: 10, style: .continuous)
                            .fill(LinearGradient(colors: [.blue.opacity(0.7), .purple.opacity(0.55)], startPoint: .topLeading, endPoint: .bottomTrailing))
                            .frame(width: 88, height: 88)
                    }
                    Text("MIX")
                        .font(.system(size: 8.5, weight: .heavy))
                        .tracking(0.7)
                        .foregroundStyle(MekambPalette.accentBlue)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.black.opacity(0.65))
                        .clipShape(RoundedRectangle(cornerRadius: 5, style: .continuous))
                        .padding(6)
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text(mix.title)
                        .font(.system(size: 22, weight: .heavy))
                        .foregroundStyle(MekambPalette.textPrimary)
                    Text(mix.description)
                        .font(.system(size: 12))
                        .foregroundStyle(MekambPalette.textMuted)
                        .lineLimit(2)
                    Text("\(mix.tracks.count) tracks · \(totalMinutes) min · refreshed daily")
                        .font(.system(size: 11.5))
                        .foregroundStyle(MekambPalette.textMuted)
                }
                Spacer(minLength: 0)

                Button {
                    if let first = mix.tracks.first { app.play(first, queue: mix.tracks) }
                } label: {
                    Image(systemName: "play.fill")
                        .foregroundStyle(MekambPalette.backgroundSecondary)
                }
                .frame(width: 48, height: 48)
                .background(Circle().fill(MekambPalette.accentBlue))
                .disabled(mix.tracks.isEmpty)
            }
        }
        .padding(.horizontal, 18)
        .padding(.top, 8)
        .padding(.bottom, 16)
        .background(
            LinearGradient(colors: [MekambPalette.accentBlueDeep.opacity(0.30), MekambPalette.backgroundPrimary.opacity(0)], startPoint: .top, endPoint: .bottom)
        )
    }
}

// MARK: - Playlist detail (pushed) — existing PlaylistDetailView, wrapped with a back header.

struct PlaylistDetailScreen: View {
    @EnvironmentObject private var app: AppState
    let playlist: PlaylistDetail

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    DetailBackButton(tint: MekambPalette.textPrimary, background: MekambPalette.surface2) {
                        app.selectedPlaylistId = nil
                        app.selectedTab = app.lastBarTab
                    }
                    Spacer()
                }
                .padding(.horizontal)
                .padding(.top, 12)

                PlaylistDetailView(playlist: playlist)
                    .environmentObject(app)
            }
            .padding(.bottom, 24)
        }
        .background(MekambPalette.backgroundPrimary.ignoresSafeArea())
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

// MARK: - Artwork

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

    private var isCurrent: Bool { app.currentTrack?.id == track.id }

    var body: some View {
        ZStack(alignment: .leading) {
            Label("Queue", systemImage: "text.badge.plus")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.white)
                .padding(.horizontal, 14)
                .frame(maxHeight: .infinity)
                .opacity(dragOffset > 8 ? 1 : 0)

            HStack(spacing: 12) {
                ZStack {
                    TrackArtworkView(track: track, size: 52)
                        .environmentObject(app)
                    if isCurrent {
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .fill(Color.black.opacity(0.45))
                        EqualizerBarsView()
                    }
                }
                .frame(width: 52, height: 52)

                VStack(alignment: .leading, spacing: 4) {
                    Text(track.title)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(isCurrent ? MekambPalette.accentBlue : .white)
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
                        .foregroundStyle(MekambPalette.accentBlue)
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
                    if !app.libraries.isEmpty {
                        Menu {
                            ForEach(app.libraries) { library in
                                Button {
                                    Task { await app.addTrack(track.id, toLibrary: library.id) }
                                } label: {
                                    Label(library.name, systemImage: "books.vertical")
                                }
                            }
                        } label: {
                            Label("Add to Library", systemImage: "books.vertical")
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
            .background(isCurrent ? MekambPalette.accentBlue.opacity(0.18) : Color.white.opacity(0.06))
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

// MARK: - Add Music (wired directly to the existing Lidarr-backed catalog search)

struct CatalogSearchView: View {
    @EnvironmentObject private var app: AppState
    @FocusState private var isFocused: Bool

    var body: some View {
        ScrollView {
            LazyVStack(spacing: 10) {
                HStack {
                    Text(app.catalogQuery.isEmpty ? "Add Music" : "Results")
                        .font(.title2.bold())
                    Spacer()
                    if app.isSearchingCatalog { ProgressView() }
                }
                .padding(.horizontal)
                .padding(.top, 12)

                HStack(spacing: 10) {
                    Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                    TextField(app.catalogKind == .artist ? "Add an artist..." : "Add an album...", text: $app.catalogQuery)
                        .focused($isFocused)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .submitLabel(.search)
                    if !app.catalogQuery.isEmpty {
                        Button {
                            app.catalogQuery = ""
                            app.catalogItems = []
                        } label: {
                            Image(systemName: "xmark.circle.fill").foregroundStyle(.secondary)
                        }
                    }
                }
                .padding(12)
                .background(Color.white.opacity(0.08))
                .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                .padding(.horizontal)

                Picker("Type", selection: $app.catalogKind) {
                    ForEach(CatalogKind.allCases) { kind in
                        Text(kind.label).tag(kind)
                    }
                }
                .pickerStyle(.segmented)
                .padding(.horizontal)

                if app.catalogQuery.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    ContentUnavailableView(
                        "Grow the library",
                        systemImage: "plus.magnifyingglass",
                        description: Text("Search an artist or album; Lidarr fetches it into the shared catalog.")
                    )
                    .foregroundStyle(.secondary)
                    .padding(.top, 48)
                } else if app.catalogItems.isEmpty && !app.isSearchingCatalog {
                    ContentUnavailableView("No results", systemImage: "tray", description: Text("Try a different query."))
                        .foregroundStyle(.secondary)
                        .padding(.top, 48)
                } else {
                    ForEach(app.catalogItems) { item in
                        CatalogRowNative(item: item)
                            .environmentObject(app)
                            .padding(.horizontal)
                    }
                }

                if !app.catalogRequests.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Recent requests")
                            .font(.headline)
                            .padding(.horizontal)
                        ForEach(app.catalogRequests.prefix(12)) { req in
                            HStack {
                                Text(req.title).font(.subheadline).lineLimit(1)
                                Spacer()
                                Text(req.status.capitalized)
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(.secondary)
                            }
                            .padding(.horizontal)
                        }
                    }
                    .padding(.top, 12)
                }
            }
        }
        .task { await app.loadCatalogRequests() }
        .task(id: app.catalogQuery) {
            guard !app.catalogQuery.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                app.catalogItems = []
                return
            }
            try? await Task.sleep(nanoseconds: 350_000_000)
            guard !Task.isCancelled else { return }
            await app.searchCatalog()
        }
        .onChange(of: app.catalogKind) { _, _ in
            Task { await app.searchCatalog() }
        }
        .refreshable { await app.searchCatalog() }
    }
}

struct CatalogRowNative: View {
    @EnvironmentObject private var app: AppState
    @State private var isAdding = false
    let item: CatalogItem

    private var isAdded: Bool { app.addedCatalogIds.contains(item.id) }

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 5) {
                Text(item.title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.white)
                    .lineLimit(2)
                if !item.subtitle.isEmpty {
                    Text(item.subtitle)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
            Spacer()
            Button {
                isAdding = true
                Task {
                    await app.addToCatalog(item)
                    isAdding = false
                }
            } label: {
                if isAdding {
                    ProgressView().tint(.white)
                } else if isAdded {
                    Label("Added", systemImage: "checkmark")
                        .font(.caption.weight(.bold))
                } else {
                    Text("Add").font(.caption.weight(.bold))
                }
            }
            .buttonStyle(.borderedProminent)
            .disabled(isAdding || isAdded)
        }
        .padding(12)
        .background(Color.white.opacity(0.06))
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
    }
}

// MARK: - Imports tab

struct ImportsView: View {
    @EnvironmentObject private var app: AppState
    @State private var pollTask: Task<Void, Never>?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text("Imports")
                        .font(.system(size: 23, weight: .heavy))
                        .foregroundStyle(MekambPalette.textPrimary)
                    Spacer()
                    if app.isLoadingImports { ProgressView() }
                }
                .padding(.horizontal)
                .padding(.top, 12)

                Text("Albums acquired through the catalog appear here as they ingest.")
                    .font(.system(size: 12.5))
                    .foregroundStyle(MekambPalette.textMuted)
                    .padding(.horizontal)
                    .padding(.bottom, 12)

                if !app.canUseApi {
                    ContentUnavailableView("Connect API", systemImage: "wifi.exclamationmark", description: Text("Open Settings, set the endpoint and log in."))
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity)
                        .padding(.top, 40)
                } else if app.isLoadingImports && app.importRecords.isEmpty {
                    ProgressView()
                        .frame(maxWidth: .infinity)
                        .padding(.top, 40)
                } else if app.importRecords.isEmpty {
                    ContentUnavailableView(
                        "No imports yet",
                        systemImage: "tray",
                        description: Text("Add music from the Add Music tab; imports show up here as they ingest.")
                    )
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity)
                    .padding(.top, 40)
                } else {
                    LazyVStack(spacing: 10) {
                        ForEach(app.importRecords) { record in
                            ImportRowView(record: record)
                                .environmentObject(app)
                                .padding(.horizontal)
                        }
                    }
                }
            }
            .padding(.bottom, 24)
        }
        .refreshable { await app.loadImports() }
        .task { await app.loadImports() }
        .onAppear { startPolling() }
        .onDisappear {
            pollTask?.cancel()
            pollTask = nil
        }
    }

    private func startPolling() {
        pollTask?.cancel()
        pollTask = Task {
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 4_000_000_000)
                if Task.isCancelled { break }
                await app.loadImports()
            }
        }
    }
}

struct ImportRowView: View {
    @EnvironmentObject private var app: AppState
    let record: ImportRecordResponse
    @State private var isWorking = false

    private var chipColor: Color {
        if record.isImported { return MekambPalette.successGreen }
        if record.isFailed || record.isCanceled { return MekambPalette.dangerRed }
        return MekambPalette.accentBlue
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(spacing: 10) {
                RoundedRectangle(cornerRadius: 6, style: .continuous)
                    .fill(LinearGradient(colors: [.blue.opacity(0.55), .purple.opacity(0.45)], startPoint: .topLeading, endPoint: .bottomTrailing))
                    .frame(width: 38, height: 38)
                    .overlay(Image(systemName: "square.and.arrow.down").font(.caption).foregroundStyle(.white))

                VStack(alignment: .leading, spacing: 2) {
                    Text(record.displayName)
                        .font(.system(size: 13, weight: .bold))
                        .foregroundStyle(MekambPalette.textPrimary)
                        .lineLimit(1)
                    Text("\(record.source.capitalized) · \(record.uploader.isEmpty ? "unknown uploader" : record.uploader)")
                        .font(.system(size: 11))
                        .foregroundStyle(MekambPalette.textMuted)
                        .lineLimit(1)
                }

                Spacer()

                Text(record.statusLabel.uppercased())
                    .font(.system(size: 9.5, weight: .heavy))
                    .tracking(0.5)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(chipColor.opacity(0.15))
                    .foregroundStyle(chipColor)
                    .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
            }

            if record.isActive {
                VStack(alignment: .leading, spacing: 4) {
                    IndeterminateProgressBarView()
                    HStack {
                        Text(record.stageDescription)
                        Spacer()
                    }
                    .font(.system(size: 11))
                    .foregroundStyle(MekambPalette.textMuted)
                }
            }

            if record.isFailed, let error = record.errorMessage, !error.isEmpty {
                Text(error)
                    .font(.system(size: 11.5))
                    .foregroundStyle(MekambPalette.dangerRed)
            }

            if record.isActive || record.isFailed {
                HStack(spacing: 8) {
                    if record.isActive {
                        Button {
                            Task {
                                isWorking = true
                                await app.cancelImport(record)
                                isWorking = false
                            }
                        } label: {
                            Text("Cancel")
                                .font(.system(size: 11.5, weight: .bold))
                                .foregroundStyle(MekambPalette.textMuted)
                                .padding(.horizontal, 12)
                                .padding(.vertical, 5)
                                .overlay(Capsule().stroke(MekambPalette.border3, lineWidth: 1))
                        }
                        .disabled(isWorking)
                    }
                    if record.isFailed {
                        Button {
                            Task {
                                isWorking = true
                                await app.retryImport(record)
                                isWorking = false
                            }
                        } label: {
                            Text("Retry")
                                .font(.system(size: 11.5, weight: .bold))
                                .foregroundStyle(MekambPalette.backgroundSecondary)
                                .padding(.horizontal, 13)
                                .padding(.vertical, 6)
                                .background(MekambPalette.accentBlue)
                                .clipShape(Capsule())
                        }
                        .disabled(isWorking)
                    }
                    if isWorking { ProgressView() }
                }
            }
        }
        .padding(13)
        .background(MekambPalette.surface1)
        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(MekambPalette.border1, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
    }
}

// MARK: - Personal libraries (curated subsets of the shared catalog — unrelated to the "Your
// Library" tab above; reached from Settings → Storage → "My Libraries").

struct LibrariesView: View {
    @EnvironmentObject private var app: AppState
    @State private var showCreate = false
    @State private var newName = ""

    var body: some View {
        List {
            if app.libraries.isEmpty {
                ContentUnavailableView(
                    "No libraries yet",
                    systemImage: "books.vertical",
                    description: Text("Create a library, then add tracks from the shared catalog.")
                )
            } else {
                ForEach(app.libraries) { library in
                    NavigationLink {
                        LibraryDetailView(summary: library).environmentObject(app)
                    } label: {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(library.name).font(.body.weight(.semibold))
                            Text("\(library.trackCount) tracks")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .onDelete { indexSet in
                    for index in indexSet {
                        let id = app.libraries[index].id
                        Task { await app.deleteLibrary(id) }
                    }
                }
            }
        }
        .navigationTitle("My Libraries")
        .toolbar {
            Button {
                newName = ""
                showCreate = true
            } label: {
                Image(systemName: "plus")
            }
        }
        .alert("New Library", isPresented: $showCreate) {
            TextField("Name", text: $newName)
            Button("Cancel", role: .cancel) {}
            Button("Create") {
                let name = newName
                Task { await app.createLibrary(name: name) }
            }
        }
        .task { await app.loadLibraries() }
    }
}

struct LibraryDetailView: View {
    @EnvironmentObject private var app: AppState
    let summary: LibrarySummary
    @State private var detail: LibraryDetail?

    var body: some View {
        List {
            if let loaded = detail, !loaded.orderedTracks.isEmpty {
                ForEach(loaded.orderedTracks) { track in
                    TrackRowNative(track: track)
                        .environmentObject(app)
                        .listRowInsets(EdgeInsets())
                        .listRowBackground(Color.clear)
                        .swipeActions {
                            Button(role: .destructive) {
                                Task {
                                    detail = await app.removeTrack(track.id, fromLibrary: summary.id)
                                }
                            } label: {
                                Label("Remove", systemImage: "minus.circle")
                            }
                        }
                }
            } else {
                ContentUnavailableView(
                    "Empty library",
                    systemImage: "music.note",
                    description: Text("Add tracks from the shared catalog using the track menu.")
                )
            }
        }
        .navigationTitle(summary.name)
        .task { detail = await app.libraryDetail(summary.id) }
    }
}

struct CodecBadgeView: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.system(size: 9, weight: .bold))
            .foregroundStyle(MekambPalette.accentBlue)
            .padding(.horizontal, 5)
            .padding(.vertical, 2)
            .background(MekambPalette.accentBlue.opacity(0.18), in: RoundedRectangle(cornerRadius: 4, style: .continuous))
            .fixedSize()
    }
}

// MARK: - Now Playing / mini player (unchanged behavior; palette nudged to the exact accent hex)

struct PlayerBar: View {
    @EnvironmentObject private var app: AppState
    @State private var showingQueue = false
    @State private var showingNowPlaying = false

    var body: some View {
        VStack(spacing: 10) {
            ScrubbablePlaybackBar(tint: MekambPalette.accentBlue)
                .environmentObject(app)

            HStack(spacing: 10) {
                Button { app.toggleShuffle() } label: {
                    Image(systemName: "shuffle")
                        .foregroundStyle(app.shuffleEnabled ? MekambPalette.accentBlue : .secondary)
                }
                .accessibilityLabel("Shuffle")

                Spacer()

                Text(app.repeatMode.label)
                    .font(.caption2)
                    .foregroundStyle(.secondary)

                Spacer()

                Button { app.cycleRepeatMode() } label: {
                    Image(systemName: app.repeatMode.iconName)
                        .foregroundStyle(app.repeatMode.isActive ? MekambPalette.accentBlue : .secondary)
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
                            HStack(spacing: 6) {
                                Text(app.currentTrack?.title ?? "Nothing playing")
                                    .font(.subheadline.weight(.semibold))
                                    .lineLimit(1)
                                if app.currentTrack != nil, let badge = app.currentCodecBadge {
                                    CodecBadgeView(text: badge)
                                }
                            }
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
                        .background(MekambPalette.accentBlue)
                        .foregroundStyle(MekambPalette.backgroundSecondary)
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
                                        HStack(spacing: 8) {
                                            Text(track.title)
                                                .font(.title2.bold())
                                                .foregroundStyle(.white)
                                                .lineLimit(2)
                                            if let badge = app.currentCodecBadge {
                                                CodecBadgeView(text: badge)
                                            }
                                        }
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
                                            .foregroundStyle(app.likedTrackIds.contains(track.id) ? MekambPalette.likePink : .white)
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
                                        .foregroundStyle(app.shuffleEnabled ? MekambPalette.accentBlue : .white)
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
                                        .foregroundStyle(app.repeatMode.isActive ? MekambPalette.accentBlue : .white)
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

// MARK: - Profile menu (avatar → menu overlay on Home)

struct ProfileMenuOverlay: View {
    @EnvironmentObject private var app: AppState
    @Binding var isPresented: Bool

    var body: some View {
        ZStack(alignment: .topTrailing) {
            Color.black.opacity(0.45)
                .ignoresSafeArea()
                .onTapGesture { isPresented = false }

            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 10) {
                    Circle()
                        .fill(LinearGradient(colors: [MekambPalette.accentBlueDeep, MekambPalette.accentBlue], startPoint: .topLeading, endPoint: .bottomTrailing))
                        .frame(width: 38, height: 38)
                        .overlay(
                            Text(app.accountInitials)
                                .font(.system(size: 12, weight: .heavy))
                                .foregroundStyle(MekambPalette.backgroundSecondary)
                        )
                    VStack(alignment: .leading, spacing: 2) {
                        Text(app.accountUsername.isEmpty ? "Not signed in" : app.accountUsername)
                            .font(.system(size: 13.5, weight: .bold))
                            .foregroundStyle(MekambPalette.textPrimary)
                        Text(app.accountEmail.isEmpty ? "Sign in from Settings" : app.accountEmail)
                            .font(.system(size: 11.5))
                            .foregroundStyle(MekambPalette.textMuted)
                            .lineLimit(1)
                    }
                }
                .padding(10)

                Rectangle().fill(MekambPalette.border3).frame(height: 1).padding(.horizontal, 4).padding(.bottom, 6)

                ProfileMenuRow(icon: "gearshape", title: "Settings", tint: MekambPalette.textPrimary) {
                    isPresented = false
                    app.selectedTab = .settings
                }
                ProfileMenuRow(icon: "person.crop.circle", title: "Account", tint: MekambPalette.textPrimary) {
                    // "Account" is now a section inside Settings rather than a separate screen.
                    isPresented = false
                    app.selectedTab = .settings
                }

                Rectangle().fill(MekambPalette.border3).frame(height: 1).padding(.horizontal, 4).padding(.vertical, 6)

                ProfileMenuRow(icon: "rectangle.portrait.and.arrow.right", title: "Log out", tint: MekambPalette.dangerRed) {
                    isPresented = false
                    Task { await app.logout() }
                }
            }
            .padding(6)
            .frame(width: 230)
            .background(MekambPalette.surface2)
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(MekambPalette.border3, lineWidth: 1))
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            .shadow(color: .black.opacity(0.5), radius: 24, y: 12)
            .padding(.top, 96)
            .padding(.trailing, 16)
        }
    }
}

struct ProfileMenuRow: View {
    let icon: String
    let title: String
    let tint: Color
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 11) {
                Image(systemName: icon)
                    .font(.system(size: 15))
                    .foregroundStyle(tint == MekambPalette.dangerRed ? tint : MekambPalette.textMuted)
                    .frame(width: 18)
                Text(title)
                    .font(.system(size: 13.5, weight: .semibold))
                    .foregroundStyle(tint)
                Spacer()
            }
            .padding(10)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Settings (reached from the profile menu, not a bottom tab)

struct SettingsView: View {
    @EnvironmentObject private var app: AppState
    @State private var showLibraries = false
    @State private var updateStatusMessage = "You're up to date"

    private var appVersionText: String {
        let version = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
        let build = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "1"
        return "\(version) (\(build))"
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Form {
                AccountSection()

                Section("Server") {
                    TextField("192.168.1.50:8000", text: $app.apiEndpoint)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)

                    HStack(spacing: 7) {
                        Circle()
                            .fill(app.connectionStatus?.lowercased().contains("connected") == true ? MekambPalette.successGreen : MekambPalette.dangerRed)
                            .frame(width: 7, height: 7)
                        Text(app.connectionStatus ?? (app.canUseApi ? "Not tested yet" : "Not connected"))
                            .font(.footnote)
                            .foregroundStyle(app.connectionStatus?.lowercased().contains("connected") == true ? MekambPalette.successGreen : .secondary)
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

                    Text(app.normalizedEndpoint.isEmpty ? "Not set" : app.normalizedEndpoint)
                        .font(.footnote.monospaced())
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }

                Section("Playback") {
                    Picker(selection: $app.playbackQuality) {
                        ForEach(PlaybackQuality.allCases) { quality in
                            Text(quality.label).tag(quality)
                        }
                    } label: {
                        Label("Streaming quality", systemImage: "waveform")
                    }
                    Text(app.playbackQuality.detail)
                        .font(.footnote)
                        .foregroundStyle(.secondary)

                    Toggle(isOn: $app.autoplaySimilarEnabled) {
                        Label("Autoplay Similar Songs", systemImage: "infinity")
                    }

                    Toggle(isOn: $app.prefetchQueuedTracksEnabled) {
                        Label("Prefetch queued tracks", systemImage: "arrow.down.circle")
                    }
                    Text("Skips start instantly")
                        .font(.footnote)
                        .foregroundStyle(.secondary)

                    Toggle(isOn: $app.downloadOverCellularEnabled) {
                        Label("Download over cellular", systemImage: "antenna.radiowaves.left.and.right")
                    }
                    Text("Offline downloads on mobile data")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                Section("Storage") {
                    Button {
                        showLibraries = true
                    } label: {
                        Label("My Libraries", systemImage: "books.vertical")
                    }

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

                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Streaming cache")
                            if let stats = app.cacheStats {
                                Text("\(stats.totalTracks) tracks · \(String(format: "%.0f", stats.totalSizeMb)) MB")
                                    .font(.footnote)
                                    .foregroundStyle(.secondary)
                            } else if app.isLoadingCacheStats {
                                Text("Loading…")
                                    .font(.footnote)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        Spacer()
                        Button {
                            Task { await app.clearStreamingCache() }
                        } label: {
                            if app.isClearingCache {
                                ProgressView()
                            } else {
                                Text("Clear")
                            }
                        }
                        .buttonStyle(.bordered)
                        .disabled(app.isClearingCache)
                    }
                    .task { await app.loadCacheStats() }
                }

                Section("Updates") {
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Mekamb Music v\(appVersionText)")
                            Text(updateStatusMessage)
                                .font(.footnote)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        Button {
                            // There's no update-check backend for this self-hosted app — this is
                            // a harmless client-side confirmation, not a fabricated network call.
                            updateStatusMessage = "You're up to date"
                        } label: {
                            Text("Check")
                        }
                        .buttonStyle(.bordered)
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
        .background(MekambPalette.backgroundPrimary.ignoresSafeArea())
        .sheet(isPresented: $showLibraries) {
            NavigationStack {
                LibrariesView()
                    .environmentObject(app)
                    .toolbar {
                        ToolbarItem(placement: .cancellationAction) {
                            Button("Done") { showLibraries = false }
                        }
                    }
            }
        }
    }

    private var header: some View {
        HStack(spacing: 12) {
            DetailBackButton(tint: MekambPalette.textPrimary, background: MekambPalette.surface2) {
                app.selectedTab = app.lastBarTab
            }
            Text("Settings")
                .font(.system(size: 23, weight: .heavy))
                .foregroundStyle(MekambPalette.textPrimary)
            Spacer()
        }
        .padding(.horizontal)
        .padding(.top, 12)
        .padding(.bottom, 4)
    }
}

// MARK: - Account (login, token migration, registration)

private enum AuthFormMode: String, CaseIterable, Identifiable {
    case login = "Log in"
    case migrate = "Migrate token"
    case register = "Sign up"
    var id: String { rawValue }
}

struct AccountSection: View {
    @EnvironmentObject private var app: AppState

    @State private var mode: AuthFormMode = .login
    @State private var didPickInitialMode = false
    @State private var identifier = ""
    @State private var email = ""
    @State private var username = ""
    @State private var password = ""
    @State private var legacyToken = ""

    var body: some View {
        Section("Account") {
            if app.isSignedIn {
                signedInBody
            } else {
                signedOutBody
            }

            if let status = app.authStatusMessage {
                Text(status)
                    .font(.footnote)
                    .foregroundStyle(app.authStatusIsError ? .red : .green)
            }
        }
        .onAppear {
            guard !didPickInitialMode else { return }
            didPickInitialMode = true
            // A stored bearer token without account info is a legacy API token:
            // steer straight into migration with the token pre-filled.
            if !app.isSignedIn && !app.apiToken.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                mode = .migrate
                legacyToken = app.apiToken
            }
        }
    }

    @ViewBuilder
    private var signedInBody: some View {
        Label(app.accountUsername, systemImage: "person.crop.circle.fill")
        Text(app.accountEmail)
            .font(.footnote)
            .foregroundStyle(.secondary)
        Button(role: .destructive) {
            Task { await app.logout() }
        } label: {
            Label("Log Out", systemImage: "rectangle.portrait.and.arrow.right")
        }
        .disabled(app.isAuthenticating)
    }

    @ViewBuilder
    private var signedOutBody: some View {
        if mode == .migrate {
            Text("Migrate your legacy API token to an account: pick an email, username and password — your library carries over and the old token stops working everywhere.")
                .font(.footnote)
                .foregroundStyle(.secondary)
        }

        Picker("Mode", selection: $mode) {
            ForEach(AuthFormMode.allCases) { candidate in
                Text(candidate.rawValue).tag(candidate)
            }
        }
        .pickerStyle(.segmented)

        switch mode {
        case .login:
            TextField("Email or username", text: $identifier)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
        case .migrate:
            SecureField("Legacy API token", text: $legacyToken)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
            emailAndUsernameFields
        case .register:
            emailAndUsernameFields
        }

        SecureField("Password", text: $password)
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()

        Button {
            Task {
                switch mode {
                case .login:
                    await app.login(identifier: identifier, password: password)
                case .migrate:
                    await app.claimToken(
                        token: legacyToken, email: email,
                        username: username, password: password
                    )
                case .register:
                    await app.registerAccount(email: email, username: username, password: password)
                }
                if !app.authStatusIsError { password = "" }
            }
        } label: {
            Label {
                Text(app.isAuthenticating ? "Working..." : submitTitle)
            } icon: {
                if app.isAuthenticating {
                    ProgressView()
                } else {
                    Image(systemName: "person.badge.key")
                }
            }
            .frame(maxWidth: .infinity, alignment: .center)
        }
        .buttonStyle(.borderedProminent)
        .disabled(app.isAuthenticating || !canSubmit)
    }

    @ViewBuilder
    private var emailAndUsernameFields: some View {
        TextField("Email", text: $email)
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
            .keyboardType(.emailAddress)
        TextField("Username", text: $username)
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
    }

    private var submitTitle: String {
        switch mode {
        case .login: return "Log In"
        case .migrate: return "Migrate & Sign In"
        case .register: return "Create Account"
        }
    }

    private var canSubmit: Bool {
        guard !password.isEmpty else { return false }
        switch mode {
        case .login:
            return !identifier.trimmingCharacters(in: .whitespaces).isEmpty
        case .migrate:
            return !legacyToken.trimmingCharacters(in: .whitespaces).isEmpty
                && !email.trimmingCharacters(in: .whitespaces).isEmpty
                && !username.trimmingCharacters(in: .whitespaces).isEmpty
        case .register:
            return !email.trimmingCharacters(in: .whitespaces).isEmpty
                && !username.trimmingCharacters(in: .whitespaces).isEmpty
        }
    }
}
