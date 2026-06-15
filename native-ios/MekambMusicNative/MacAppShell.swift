import SwiftUI

struct MacAppShell: View {
    @EnvironmentObject private var app: AppState
    @State private var sidebarSelection: SidebarItem = .library
    @State private var searchFocused: Bool = false

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 0) {
                // Sidebar
                sidebar
                    .frame(minWidth: 220, maxWidth: 280)
                    .background(Color(nsColor: .controlBackgroundColor))

                Divider()

                // Main content area
                ZStack {
                    // Background
                    LinearGradient(
                        colors: [
                            Color(red: 0.055, green: 0.07, blue: 0.11),
                            Color(red: 0.035, green: 0.045, blue: 0.08)
                        ],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                    .ignoresSafeArea()

                    VStack(spacing: 12) {
                        // Search bar (only shown in library/albums/liked)
                        if !app.searchMode.searchesRemoteSources {
                            searchField
                                .padding(.horizontal, 12)
                                .padding(.bottom, 4)
                        }

                        // Warning / error banners
                        if let warning = app.endpointWarning, app.selectedTab == .settings {
                            HStack(spacing: 8) {
                                Image(systemName: "exclamationmark.triangle.fill")
                                    .foregroundStyle(.yellow)
                                Text(warning)
                                    .font(.caption)
                                Spacer()
                                Button {} label: {
                                    Image(systemName: "xmark")
                                        .foregroundStyle(.secondary)
                                }
                                .buttonStyle(.plain)
                            }
                            .padding(8)
                            .background(Color.yellow.opacity(0.12))
                            .clipShape(RoundedRectangle(cornerRadius: 8))
                            .padding(.horizontal, 12)
                        }

                        if let error = app.errorMessage {
                            HStack(spacing: 8) {
                                Image(systemName: "xmark.circle.fill")
                                    .foregroundStyle(.red)
                                Text(error)
                                    .font(.caption)
                                Spacer()
                                Button {} label: {
                                    Image(systemName: "xmark")
                                        .foregroundStyle(.secondary)
                                }
                                .buttonStyle(.plain)
                            }
                            .padding(8)
                            .background(Color.red.opacity(0.12))
                            .clipShape(RoundedRectangle(cornerRadius: 8))
                            .padding(.horizontal, 12)
                        }

                        // Main content
                        mainContent
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                            .padding(.horizontal, 12)
                            .padding(.top, 4)
                    }
                }

                // Queue panel (right side)
                queuePanel
                    .frame(minWidth: 200, maxWidth: 260)
                    .background(Color(nsColor: .controlBackgroundColor))
            }
            .frame(minHeight: 420)
            .task { await app.refreshLibrary() }
            .onChange(of: app.searchText) { _ in
                guard app.searchMode.searchesRemoteSources else { return }
                Task {
                    try? await Task.sleep(nanoseconds: 350_000_000)
                    await app.searchTorrents()
                }
            }
            .onChange(of: app.searchMode) { mode in
                if mode.searchesRemoteSources {
                    app.selectedAlbumId = nil
                    app.torrents = []
                    Task { await app.searchTorrents() }
                }
            }
            .onChange(of: app.selectedTab) { tab in
                if tab != .albums { app.selectedAlbumId = nil }
            }

            // Bottom player bar
            PlayerBarView()
                .environmentObject(app)
        }
        .background(Color(red: 0.05, green: 0.06, blue: 0.10))
        .onChange(of: sidebarSelection) { selection in
            if selection == .albums {
                app.selectedTab = .albums
            } else if selection == .library {
                app.selectedTab = .library
            } else if selection == .liked {
                app.selectedTab = .liked
            }
        }
        .onChange(of: app.selectedTab) { tab in
            if tab == .library { sidebarSelection = .library }
            if tab == .albums { sidebarSelection = .albums }
            if tab == .liked { sidebarSelection = .liked }
        }
    }

    // MARK: - Sidebar

    @ViewBuilder
    private var sidebar: some View {
        List(selection: $sidebarSelection) {
            Section("Library") {
                Label("Library", systemImage: "music.note.list")
                    .tag(SidebarItem.library)
                Label("Albums", systemImage: "music.album")
                    .tag(SidebarItem.albums)
                Label("Liked", systemImage: "heart.fill")
                    .tag(SidebarItem.liked)
            }

            Section("Search") {
                Label("Torrents", systemImage: "cloud.fill")
                    .tag(SidebarItem.torrentSearch)
                Label("Indexers", systemImage: "magnifyingglass")
                    .tag(SidebarItem.indexerSearch)
            }

            Section("System") {
                Label("Queue", systemImage: "list.bullet")
                    .tag(SidebarItem.queue)
                Label("Settings", systemImage: "gearshape.2")
                    .tag(SidebarItem.settings)
            }
        }
        .listStyle(.sidebar)
        .frame(minWidth: 0, maxWidth: 280)
        .padding(.bottom, 8)
    }

    // MARK: - Search Field

    @ViewBuilder
    private var searchField: some View {
        HStack(spacing: 10) {
            Image(systemName: "magnifyingglass")
                .foregroundStyle(.secondary)
                .frame(width: 20)

            TextField("Search", text: $app.searchText)
                .focused($searchFocused)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .submitLabel(.search)
                .onSubmit {
                    app.searchText = ""
                    app.torrents = []
                    if app.searchMode.searchesRemoteSources {
                        Task { await app.searchTorrents() }
                    }
                }

            Spacer()

            if !app.searchText.isEmpty {
                Button {} label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(10)
        .background(Color(nsColor: .textBackgroundColor).opacity(0.6))
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    // MARK: - Main Content

    @ViewBuilder
    private var mainContent: some View {
        Group {
            switch sidebarSelection {
            case .library:
                LibraryView()
            case .albums:
                AlbumsView()
            case .liked:
                LikedView()
            case .torrentSearch:
                TorrentSearchView()
            case .indexerSearch:
                IndexerSearchView()
            case .queue:
                QueueView()
            case .settings:
                SettingsView()
            }
        }
    }

    // MARK: - Queue Panel

    @ViewBuilder
    private var queuePanel: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Queue")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .textCase(.uppercase)
                .padding(.horizontal, 8)

            Divider()

            ScrollView {
                LazyVStack(spacing: 6) {
                    if let current = app.currentTrack {
                        Text("Now Playing")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .textCase(.uppercase)
                            .padding(.horizontal, 8)
                            .padding(.top, 8)

                        QueueMiniTrack(track: current, isCurrent: true)
                    }

                    if !app.upcomingQueueTracks.isEmpty {
                        Text("Up Next")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .textCase(.uppercase)
                            .padding(.horizontal, 8)
                            .padding(.top, 8)

                        ForEach(app.upcomingQueueTracks) { track in
                            QueueMiniTrack(track: track, isCurrent: false)
                        }
                    }
                }
            }
            .scrollContentBackground(.hidden)

            Divider()

            HStack(spacing: 4) {
                Button("Clear Upcoming") {
                    app.clearUpcomingQueue()
                }
                .buttonStyle(.borderless)
                .font(.caption2)
                .foregroundStyle(.secondary)

                Spacer()
            }
            .padding(.vertical, 6)
            .padding(.horizontal, 8)
        }
        .background(Color(nsColor: .controlBackgroundColor))
    }
}

// MARK: - Sidebar Item

enum SidebarItem: String, CaseIterable, Identifiable {
    case library, albums, liked, torrentSearch, indexerSearch, queue, settings
    var id: String { rawValue }
}
