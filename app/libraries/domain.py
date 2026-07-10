from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


class LibraryNotFound(RuntimeError):
    pass


class LibraryTrackNotFound(RuntimeError):
    pass


class TrackNotFound(RuntimeError):
    pass


@dataclass(frozen=True)
class LibrarySummary:
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
class LibraryTrackItem:
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
class LibraryDetail:
    id: UUID
    name: str
    tracks: list[LibraryTrackItem]
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


class LibraryRepository(Protocol):
    async def create(self, *, name: str) -> LibraryDetail:
        ...

    async def list(self, *, limit: int, offset: int) -> list[LibrarySummary]:
        ...

    async def get(self, library_id: UUID) -> LibraryDetail:
        ...

    async def update(self, *, library_id: UUID, name: str) -> LibraryDetail:
        ...

    async def delete(self, library_id: UUID) -> None:
        ...

    async def add_track(self, *, library_id: UUID, track_id: UUID) -> LibraryDetail:
        ...

    async def remove_track(self, *, library_id: UUID, track_id: UUID) -> LibraryDetail:
        ...
