from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.auth import DEFAULT_API_KEY_ID
from app.imports.domain import ImportStatus


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


class ImportJob(Base):
    __tablename__ = "import_jobs"
    __table_args__ = (UniqueConstraint("info_hash", name="uq_import_jobs_info_hash"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source: Mapped[str] = mapped_column(String(64), default="personal_1337x", nullable=False)
    torrent_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    info_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    magnet_link: Mapped[str] = mapped_column(Text, nullable=False)
    uploader: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default=ImportStatus.QUEUED.value,
        nullable=False,
        index=True,
    )
    quarantine_path: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "source": self.source,
            "torrent_id": self.torrent_id,
            "info_hash": self.info_hash,
            "uploader": self.uploader,
            "source_url": self.source_url,
            "status": self.status,
            "quarantine_path": self.quarantine_path,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class Track(Base):
    __tablename__ = "tracks"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    artist: Mapped[str | None] = mapped_column(String(512))
    album: Mapped[str | None] = mapped_column(String(512))
    storage_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str | None] = mapped_column(String(128))
    codec: Mapped[str | None] = mapped_column(String(128))

    # Float zamiast int — pliki < 1s nie są zaokrąglane do 0
    duration_seconds: Mapped[float | None] = mapped_column(Float)

    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    # Klucz do okładki w library storage (współdzielony dla całego albumu/importu)
    cover_key: Mapped[str | None] = mapped_column(Text)

    source_import_id: Mapped[UUID | None] = mapped_column(index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Aktualizowane przy każdym streamowaniu — używane przez cache TTL cleanup
    last_accessed: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "storage_key": self.storage_key,
            "original_filename": self.original_filename,
            "media_type": self.media_type,
            "codec": self.codec,
            "duration_seconds": self.duration_seconds,
            "size_bytes": self.size_bytes,
            "cover_key": self.cover_key,
            "source_import_id": str(self.source_import_id) if self.source_import_id else None,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
        }


class LikedTrack(Base):
    __tablename__ = "liked_tracks"
    __table_args__ = (UniqueConstraint("api_key_id", "track_id", name="uq_liked_tracks_api_key_track"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    api_key_id: Mapped[str] = mapped_column(
        String(64),
        default=DEFAULT_API_KEY_ID,
        nullable=False,
        index=True,
    )
    track_id: Mapped[UUID] = mapped_column(ForeignKey("tracks.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TrackPlay(Base):
    __tablename__ = "track_plays"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    api_key_id: Mapped[str] = mapped_column(
        String(64),
        default=DEFAULT_API_KEY_ID,
        nullable=False,
        index=True,
    )
    track_id: Mapped[UUID] = mapped_column(ForeignKey("tracks.id"), nullable=False, index=True)
    played_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    listen_ratio: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(64), default="api", nullable=False, index=True)


class PersonalizationSignal(Base):
    __tablename__ = "personalization_signals"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    api_key_id: Mapped[str] = mapped_column(
        String(64),
        default=DEFAULT_API_KEY_ID,
        nullable=False,
        index=True,
    )
    track_id: Mapped[UUID] = mapped_column(ForeignKey("tracks.id"), nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="api", nullable=False, index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class TrackAudioFeature(Base):
    __tablename__ = "track_audio_features"
    __table_args__ = (UniqueConstraint("track_id", name="uq_track_audio_features_track"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    track_id: Mapped[UUID] = mapped_column(ForeignKey("tracks.id"), nullable=False, index=True)
    tempo: Mapped[float | None] = mapped_column(Float)
    energy: Mapped[float | None] = mapped_column(Float)
    chroma: Mapped[float | None] = mapped_column(Float)
    spectral_centroid: Mapped[float | None] = mapped_column(Float)
    mfcc: Mapped[list[float]] = mapped_column(JSON, default=list, nullable=False)
    mood_tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    extractor: Mapped[str] = mapped_column(String(64), default="local", nullable=False)
    features_version: Mapped[str] = mapped_column(String(32), default="v1", nullable=False)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    def vector(self) -> list[float]:
        values: list[float] = []
        values.extend(float(value) for value in (self.mfcc or [])[:13])
        values.extend(
            float(value or 0.0)
            for value in (self.tempo, self.energy, self.chroma, self.spectral_centroid)
        )
        return values


class PlaybackState(Base):
    __tablename__ = "playback_states"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default="default")
    current_track_id: Mapped[UUID | None] = mapped_column(ForeignKey("tracks.id"), index=True)
    position_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_playing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    repeat_mode: Mapped[str] = mapped_column(String(32), default="off", nullable=False)
    shuffle: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active_device_id: Mapped[str | None] = mapped_column(String(255))
    active_device_name: Mapped[str | None] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class PlaybackQueueItem(Base):
    __tablename__ = "playback_queue_items"
    __table_args__ = (UniqueConstraint("state_id", "position", name="uq_playback_queue_position"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    state_id: Mapped[str] = mapped_column(
        ForeignKey("playback_states.id"),
        default="default",
        nullable=False,
        index=True,
    )
    track_id: Mapped[UUID] = mapped_column(ForeignKey("tracks.id"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserAction(Base):
    __tablename__ = "user_actions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    api_key_id: Mapped[str] = mapped_column(
        String(64),
        default=DEFAULT_API_KEY_ID,
        nullable=False,
        index=True,
    )
    action_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_id: Mapped[str | None] = mapped_column(String(255), index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    origin_instance_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    apply_error: Mapped[str | None] = mapped_column(Text)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "api_key_id": self.api_key_id,
            "action_type": self.action_type,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "payload": self.payload,
            "origin_instance_id": self.origin_instance_id,
            "created_at": self.created_at.isoformat(),
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "apply_error": self.apply_error,
        }


class Playlist(Base):
    __tablename__ = "playlists"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    api_key_id: Mapped[str] = mapped_column(
        String(64),
        default=DEFAULT_API_KEY_ID,
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PlaylistTrack(Base):
    __tablename__ = "playlist_tracks"
    __table_args__ = (UniqueConstraint("playlist_id", "track_id", name="uq_playlist_tracks_track"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    playlist_id: Mapped[UUID] = mapped_column(
        ForeignKey("playlists.id"),
        nullable=False,
        index=True,
    )
    track_id: Mapped[UUID] = mapped_column(ForeignKey("tracks.id"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
