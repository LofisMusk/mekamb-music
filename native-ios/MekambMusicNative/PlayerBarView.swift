import SwiftUI

struct PlayerBarView: View {
    @EnvironmentObject private var app: AppState
    @State private var progressHover = false

    var body: some View {
        HStack(spacing: 0) {
            // Left: track info + artwork
            trackInfo
                .frame(width: 280)

            Divider()
                .frame(height: 40)

            // Center: playback controls
            playbackControls
                .frame(maxWidth: 480)

            Divider()
                .frame(height: 40)

            // Right: volume + extra
            extraControls
                .frame(width: 260)
        }
        .frame(height: 64)
        .padding(.horizontal, 4)
        .background(
            LinearGradient(
                colors: [
                    Color(nsColor: .controlBackgroundColor).opacity(0.9),
                    Color(nsColor: .controlBackgroundColor)
                ],
                startPoint: .top,
                endPoint: .bottom
            )
        )
    }

    // MARK: - Track Info

    @ViewBuilder
    private var trackInfo: some View {
        HStack(spacing: 10) {
            if let track = app.currentTrack {
                TrackArtworkView(track: track, size: 48)
                    .environmentObject(app)
                    .cornerRadius(6)

                VStack(alignment: .leading, spacing: 2) {
                    Text(track.title)
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(.primary)
                        .lineLimit(1)

                    Text(track.displayArtist)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            } else {
                Image(systemName: "music.note")
                    .foregroundStyle(.tertiary)
                    .font(.title2)

                Text("No track playing")
                    .font(.subheadline)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.leading, 14)
    }

    // MARK: - Playback Controls

    @ViewBuilder
    private var playbackControls: some View {
        VStack(spacing: 4) {
            // Controls
            HStack(spacing: 8) {
                Button {
                    app.shuffleMode = app.shuffleMode == .on ? .off : .on
                } label: {
                    Image(systemName: app.shuffleMode == .on ? "shuffle.slash.fill" : "shuffle")
                }
                .buttonStyle(.plain)
                .foregroundStyle(app.shuffleMode == .on ? .blue : .secondary)
                .frame(width: 32)

                Button {
                    app.previousTrack()
                } label: {
                    Image(systemName: "backward.fill")
                }
                .buttonStyle(.plain)
                .frame(width: 32)

                Button {
                    app.togglePlayback()
                } label: {
                    Image(systemName: app.isPlaying ? "pause.fill" : "play.fill")
                        .font(.title2)
                }
                .buttonStyle(.plain)
                .frame(width: 36, height: 36)
                .background(
                    Circle()
                        .fill(Color(nsColor: .controlBackgroundColor))
                        .shadow(color: .black.opacity(0.2), radius: 4, y: 2)
                )
                .foregroundStyle(.primary)

                Button {
                    app.nextTrack()
                } label: {
                    Image(systemName: "forward.fill")
                }
                .buttonStyle(.plain)
                .frame(width: 32)

                Button {
                    app.repeatMode = app.repeatMode == .off ? .all : app.repeatMode == .all ? .one : .off
                } label: {
                    Image(systemName: app.repeatMode == .one ? "repeat.1" : "repeat")
                }
                .buttonStyle(.plain)
                .foregroundStyle(app.repeatMode == .one ? .blue : .secondary)
                .frame(width: 32)
            }

            // Progress bar
            HStack(spacing: 6) {
                Text(app.elapsedText)
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)

                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        Rectangle()
                            .fill(Color(nsColor: .separatorColor))
                            .frame(height: 4)
                            .cornerRadius(2)

                        Rectangle()
                            .fill(
                                LinearGradient(
                                    colors: [.blue, Color(nsColor: .systemBlue)],
                                    startPoint: .leading,
                                    endPoint: .trailing
                                )
                            )
                            .frame(width: geo.size.width * app.playbackProgress, height: 4)
                            .cornerRadius(2)

                        if progressHover {
                            Circle()
                                .fill(.white)
                                .frame(width: 12, height: 12)
                                .offset(x: geo.size.width * app.playbackProgress - 6)
                                .shadow(color: .black.opacity(0.25), radius: 3, y: 1)
                        }
                    }
                    .gesture(
                        DragGesture(minimumDistance: 0)
                            .onEnded { value in
                                guard let duration = app.currentTrack?.durationSeconds,
                                      duration.isFinite, duration > 0 else { return }
                                let fraction = value.location.x / geo.size.width
                                let time = fraction * duration
                                app.seek(to: time)
                            }
                    )
                    .onHover { hover in
                        progressHover = hover
                    }
                }
                .frame(height: 4)

                Text(app.durationText)
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
            .padding(.horizontal, 12)
        }
    }

    // MARK: - Extra Controls

    @ViewBuilder
    private var extraControls: some View {
        HStack(spacing: 12) {
            // Volume
            HStack(spacing: 6) {
                Image(systemName: app.volume == 0 ? "speaker.slash.fill" :
                      app.volume < 0.5 ? "speaker.wave.1.fill" :
                      app.volume < 0.8 ? "speaker.wave.2.fill" : "speaker.wave.3.fill")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                GeometryReader { geo in
                    Rectangle()
                        .fill(Color(nsColor: .separatorColor))
                        .frame(height: 3)
                        .cornerRadius(1.5)

                    Rectangle()
                        .fill(.secondary)
                        .frame(width: geo.size.width * (app.volume ?? 0.8), height: 3)
                        .cornerRadius(1.5)
                }
                .frame(height: 3)
                .frame(width: 70)
                .gesture(
                    DragGesture(minimumDistance: 0)
                        .onEnded { value in
                            let fraction = value.location.x / 70
                            app.setVolume(fraction)
                        }
                )
                .onHover { hover in
                    // Could add hover effect
                }
            }

            Divider()

            // Now playing / Queue toggle
            Button {
                // Toggle queue visibility or focus
            } label: {
                Image(systemName: "list.bullet")
                    .foregroundStyle(.secondary)
                    .font(.caption)
            }
            .buttonStyle(.plain)
        }
        .padding(.trailing, 12)
    }
}
