from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import DEFAULT_API_KEY_ID
from app.db.models import Track, UserLibrary, UserLibraryTrack, utcnow
from app.libraries.domain import (
    LibraryDetail,
    LibraryNotFound,
    LibrarySummary,
    LibraryTrackItem,
    LibraryTrackNotFound,
    TrackNotFound,
)


class SqlAlchemyLibraryRepository:
    """Per-user library store. Every query is filtered by ``api_key_id`` so a
    user can only ever read or mutate their own libraries."""

    def __init__(self, session: AsyncSession, *, api_key_id: str = DEFAULT_API_KEY_ID) -> None:
        self.session = session
        self.api_key_id = api_key_id

    async def create(self, *, name: str) -> LibraryDetail:
        now = utcnow()
        library = UserLibrary(
            api_key_id=self.api_key_id,
            name=name,
            created_at=now,
            updated_at=now,
        )
        self.session.add(library)
        await self.session.commit()
        await self.session.refresh(library)
        return await self.get(library.id)

    async def list(self, *, limit: int, offset: int) -> list[LibrarySummary]:
        track_count = func.count(UserLibraryTrack.id).label("track_count")
        rows = await self.session.execute(
            select(UserLibrary, track_count)
            .outerjoin(UserLibraryTrack, UserLibraryTrack.library_id == UserLibrary.id)
            .where(UserLibrary.api_key_id == self.api_key_id)
            .group_by(UserLibrary.id)
            .order_by(UserLibrary.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [
            LibrarySummary(
                id=library.id,
                name=library.name,
                track_count=int(count or 0),
                created_at=library.created_at,
                updated_at=library.updated_at,
            )
            for library, count in rows
        ]

    async def get(self, library_id: UUID) -> LibraryDetail:
        library = await self._get_owned_library(library_id)
        if library is None:
            raise LibraryNotFound(f"Library {library_id} not found.")

        rows = await self.session.execute(
            select(UserLibraryTrack, Track)
            .join(Track, Track.id == UserLibraryTrack.track_id)
            .where(UserLibraryTrack.library_id == library_id)
            .order_by(UserLibraryTrack.position.asc())
        )
        return LibraryDetail(
            id=library.id,
            name=library.name,
            tracks=[
                LibraryTrackItem(
                    position=library_track.position,
                    added_at=library_track.created_at,
                    track=track.to_dict(),
                )
                for library_track, track in rows
            ],
            created_at=library.created_at,
            updated_at=library.updated_at,
        )

    async def update(self, *, library_id: UUID, name: str) -> LibraryDetail:
        library = await self._get_owned_library(library_id)
        if library is None:
            raise LibraryNotFound(f"Library {library_id} not found.")

        library.name = name
        library.updated_at = utcnow()
        await self.session.commit()
        return await self.get(library_id)

    async def delete(self, library_id: UUID) -> None:
        library = await self._get_owned_library(library_id)
        if library is None:
            raise LibraryNotFound(f"Library {library_id} not found.")

        await self.session.execute(
            delete(UserLibraryTrack).where(UserLibraryTrack.library_id == library_id)
        )
        await self.session.delete(library)
        await self.session.commit()

    async def add_track(self, *, library_id: UUID, track_id: UUID) -> LibraryDetail:
        library = await self._get_owned_library(library_id)
        if library is None:
            raise LibraryNotFound(f"Library {library_id} not found.")
        track = await self.session.get(Track, track_id)
        if track is None:
            raise TrackNotFound(f"Track {track_id} not found.")

        existing = await self.session.scalar(
            select(UserLibraryTrack).where(
                UserLibraryTrack.library_id == library_id,
                UserLibraryTrack.track_id == track_id,
            )
        )
        if existing is not None:
            return await self.get(library_id)

        max_position = await self.session.scalar(
            select(func.max(UserLibraryTrack.position)).where(
                UserLibraryTrack.library_id == library_id
            )
        )
        library.updated_at = utcnow()
        self.session.add(
            UserLibraryTrack(
                library_id=library_id,
                track_id=track_id,
                position=int(max_position or 0) + 1,
            )
        )
        await self.session.commit()
        return await self.get(library_id)

    async def remove_track(self, *, library_id: UUID, track_id: UUID) -> LibraryDetail:
        library = await self._get_owned_library(library_id)
        if library is None:
            raise LibraryNotFound(f"Library {library_id} not found.")
        library_track = await self.session.scalar(
            select(UserLibraryTrack).where(
                UserLibraryTrack.library_id == library_id,
                UserLibraryTrack.track_id == track_id,
            )
        )
        if library_track is None:
            raise LibraryTrackNotFound(f"Track {track_id} is not in library {library_id}.")

        await self.session.delete(library_track)
        await self.session.flush()
        library.updated_at = utcnow()
        await self._compact_positions(library_id)
        await self.session.commit()
        return await self.get(library_id)

    async def _compact_positions(self, library_id: UUID) -> None:
        rows = list(
            await self.session.scalars(
                select(UserLibraryTrack)
                .where(UserLibraryTrack.library_id == library_id)
                .order_by(UserLibraryTrack.position.asc())
            )
        )
        for position, library_track in enumerate(rows, start=1):
            library_track.position = position

    async def _get_owned_library(self, library_id: UUID) -> UserLibrary | None:
        return await self.session.scalar(
            select(UserLibrary).where(
                UserLibrary.id == library_id,
                UserLibrary.api_key_id == self.api_key_id,
            )
        )
