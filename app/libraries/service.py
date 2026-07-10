from __future__ import annotations

from uuid import UUID

from app.libraries.domain import LibraryDetail, LibraryRepository, LibrarySummary


class LibraryService:
    def __init__(self, *, repository: LibraryRepository) -> None:
        self.repository = repository

    async def create_library(self, *, name: str) -> LibraryDetail:
        return await self.repository.create(name=name.strip())

    async def list_libraries(self, *, limit: int, offset: int) -> list[LibrarySummary]:
        return await self.repository.list(limit=limit, offset=offset)

    async def get_library(self, library_id: UUID) -> LibraryDetail:
        return await self.repository.get(library_id)

    async def update_library(self, *, library_id: UUID, name: str) -> LibraryDetail:
        return await self.repository.update(library_id=library_id, name=name.strip())

    async def delete_library(self, library_id: UUID) -> None:
        await self.repository.delete(library_id)

    async def add_track(self, *, library_id: UUID, track_id: UUID) -> LibraryDetail:
        return await self.repository.add_track(library_id=library_id, track_id=track_id)

    async def remove_track(self, *, library_id: UUID, track_id: UUID) -> LibraryDetail:
        return await self.repository.remove_track(library_id=library_id, track_id=track_id)
