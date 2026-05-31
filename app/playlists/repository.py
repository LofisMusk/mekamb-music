from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Playlist, PlaylistTrack, Track, utcnow
from app.playlists.domain import (
    PlaylistDetail,
    PlaylistNotFound,
    PlaylistOrderMismatch,
    PlaylistSummary,
    PlaylistTrackItem,
    PlaylistTrackNotFound,
    TrackNotFound,
)


class SqlAlchemyPlaylistRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, *, name: str) -> PlaylistDetail:
        now = utcnow()
        playlist = Playlist(name=name, created_at=now, updated_at=now)
        self.session.add(playlist)
        await self.session.commit()
        await self.session.refresh(playlist)
        return await self.get(playlist.id)

    async def list(self, *, limit: int, offset: int) -> list[PlaylistSummary]:
        track_count = func.count(PlaylistTrack.id).label("track_count")
        rows = await self.session.execute(
            select(Playlist, track_count)
            .outerjoin(PlaylistTrack, PlaylistTrack.playlist_id == Playlist.id)
            .group_by(Playlist.id)
            .order_by(Playlist.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [
            PlaylistSummary(
                id=playlist.id,
                name=playlist.name,
                track_count=int(count or 0),
                created_at=playlist.created_at,
                updated_at=playlist.updated_at,
            )
            for playlist, count in rows
        ]

    async def get(self, playlist_id: UUID) -> PlaylistDetail:
        playlist = await self.session.get(Playlist, playlist_id)
        if playlist is None:
            raise PlaylistNotFound(f"Playlist {playlist_id} not found.")

        rows = await self.session.execute(
            select(PlaylistTrack, Track)
            .join(Track, Track.id == PlaylistTrack.track_id)
            .where(PlaylistTrack.playlist_id == playlist_id)
            .order_by(PlaylistTrack.position.asc())
        )
        return PlaylistDetail(
            id=playlist.id,
            name=playlist.name,
            tracks=[
                PlaylistTrackItem(
                    position=playlist_track.position,
                    added_at=playlist_track.created_at,
                    track=track.to_dict(),
                )
                for playlist_track, track in rows
            ],
            created_at=playlist.created_at,
            updated_at=playlist.updated_at,
        )

    async def update(self, *, playlist_id: UUID, name: str) -> PlaylistDetail:
        playlist = await self.session.get(Playlist, playlist_id)
        if playlist is None:
            raise PlaylistNotFound(f"Playlist {playlist_id} not found.")

        playlist.name = name
        playlist.updated_at = utcnow()
        await self.session.commit()
        return await self.get(playlist_id)

    async def delete(self, playlist_id: UUID) -> None:
        playlist = await self.session.get(Playlist, playlist_id)
        if playlist is None:
            raise PlaylistNotFound(f"Playlist {playlist_id} not found.")

        await self.session.execute(
            delete(PlaylistTrack).where(PlaylistTrack.playlist_id == playlist_id)
        )
        await self.session.delete(playlist)
        await self.session.commit()

    async def add_track(self, *, playlist_id: UUID, track_id: UUID) -> PlaylistDetail:
        playlist = await self.session.get(Playlist, playlist_id)
        if playlist is None:
            raise PlaylistNotFound(f"Playlist {playlist_id} not found.")
        track = await self.session.get(Track, track_id)
        if track is None:
            raise TrackNotFound(f"Track {track_id} not found.")

        existing = await self.session.scalar(
            select(PlaylistTrack).where(
                PlaylistTrack.playlist_id == playlist_id,
                PlaylistTrack.track_id == track_id,
            )
        )
        if existing is not None:
            return await self.get(playlist_id)

        max_position = await self.session.scalar(
            select(func.max(PlaylistTrack.position)).where(PlaylistTrack.playlist_id == playlist_id)
        )
        playlist.updated_at = utcnow()
        self.session.add(
            PlaylistTrack(
                playlist_id=playlist_id,
                track_id=track_id,
                position=int(max_position or 0) + 1,
            )
        )
        await self.session.commit()
        return await self.get(playlist_id)

    async def remove_track(self, *, playlist_id: UUID, track_id: UUID) -> PlaylistDetail:
        playlist = await self.session.get(Playlist, playlist_id)
        if playlist is None:
            raise PlaylistNotFound(f"Playlist {playlist_id} not found.")
        playlist_track = await self.session.scalar(
            select(PlaylistTrack).where(
                PlaylistTrack.playlist_id == playlist_id,
                PlaylistTrack.track_id == track_id,
            )
        )
        if playlist_track is None:
            raise PlaylistTrackNotFound(f"Track {track_id} is not in playlist {playlist_id}.")

        await self.session.delete(playlist_track)
        await self.session.flush()
        playlist.updated_at = utcnow()
        await self._compact_positions(playlist_id)
        await self.session.commit()
        return await self.get(playlist_id)

    async def reorder_tracks(self, *, playlist_id: UUID, track_ids: list[UUID]) -> PlaylistDetail:
        playlist = await self.session.get(Playlist, playlist_id)
        if playlist is None:
            raise PlaylistNotFound(f"Playlist {playlist_id} not found.")

        rows = list(
            await self.session.scalars(
                select(PlaylistTrack)
                .where(PlaylistTrack.playlist_id == playlist_id)
                .order_by(PlaylistTrack.position.asc())
            )
        )
        current_track_ids = [row.track_id for row in rows]
        if len(set(track_ids)) != len(track_ids) or set(track_ids) != set(current_track_ids):
            raise PlaylistOrderMismatch(
                "Track order must contain each current playlist track exactly once."
            )

        rows_by_track_id = {row.track_id: row for row in rows}
        for position, track_id in enumerate(track_ids, start=1):
            rows_by_track_id[track_id].position = position
        playlist.updated_at = utcnow()
        await self.session.commit()
        return await self.get(playlist_id)

    async def _compact_positions(self, playlist_id: UUID) -> None:
        rows = list(
            await self.session.scalars(
                select(PlaylistTrack)
                .where(PlaylistTrack.playlist_id == playlist_id)
                .order_by(PlaylistTrack.position.asc())
            )
        )
        for position, playlist_track in enumerate(rows, start=1):
            playlist_track.position = position
