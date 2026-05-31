from __future__ import annotations

from uuid import UUID

from app.playlists.domain import PlaylistDetail, PlaylistRepository, PlaylistSummary


class PlaylistService:
    def __init__(self, *, repository: PlaylistRepository) -> None:
        self.repository = repository

    async def create_playlist(self, *, name: str) -> PlaylistDetail:
        return await self.repository.create(name=name.strip())

    async def list_playlists(self, *, limit: int, offset: int) -> list[PlaylistSummary]:
        return await self.repository.list(limit=limit, offset=offset)

    async def get_playlist(self, playlist_id: UUID) -> PlaylistDetail:
        return await self.repository.get(playlist_id)

    async def update_playlist(self, *, playlist_id: UUID, name: str) -> PlaylistDetail:
        return await self.repository.update(playlist_id=playlist_id, name=name.strip())

    async def delete_playlist(self, playlist_id: UUID) -> None:
        await self.repository.delete(playlist_id)

    async def add_track(self, *, playlist_id: UUID, track_id: UUID) -> PlaylistDetail:
        return await self.repository.add_track(playlist_id=playlist_id, track_id=track_id)

    async def remove_track(self, *, playlist_id: UUID, track_id: UUID) -> PlaylistDetail:
        return await self.repository.remove_track(playlist_id=playlist_id, track_id=track_id)

    async def reorder_tracks(self, *, playlist_id: UUID, track_ids: list[UUID]) -> PlaylistDetail:
        return await self.repository.reorder_tracks(playlist_id=playlist_id, track_ids=track_ids)
