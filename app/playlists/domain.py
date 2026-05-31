from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


class PlaylistNotFound(RuntimeError):
    pass


class PlaylistTrackNotFound(RuntimeError):
    pass


class PlaylistOrderMismatch(RuntimeError):
    pass


class TrackNotFound(RuntimeError):
    pass


@dataclass(frozen=True)
class PlaylistSummary:
    id: UUID
    name: str
    track_count: int
    created_at: datetime
    updated_at: datetime

    def to_dict(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "name": self.name,
            "track_count": self.track_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True)
class PlaylistTrackItem:
    position: int
    added_at: datetime
    track: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "position": self.position,
            "added_at": self.added_at.isoformat(),
            "track": self.track,
        }


@dataclass(frozen=True)
class PlaylistDetail:
    id: UUID
    name: str
    tracks: list[PlaylistTrackItem]
    created_at: datetime
    updated_at: datetime

    def to_dict(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "name": self.name,
            "tracks": [track.to_dict() for track in self.tracks],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class PlaylistRepository(Protocol):
    async def create(self, *, name: str) -> PlaylistDetail:
        ...

    async def list(self, *, limit: int, offset: int) -> list[PlaylistSummary]:
        ...

    async def get(self, playlist_id: UUID) -> PlaylistDetail:
        ...

    async def update(self, *, playlist_id: UUID, name: str) -> PlaylistDetail:
        ...

    async def delete(self, playlist_id: UUID) -> None:
        ...

    async def add_track(self, *, playlist_id: UUID, track_id: UUID) -> PlaylistDetail:
        ...

    async def remove_track(self, *, playlist_id: UUID, track_id: UUID) -> PlaylistDetail:
        ...

    async def reorder_tracks(self, *, playlist_id: UUID, track_ids: list[UUID]) -> PlaylistDetail:
        ...
