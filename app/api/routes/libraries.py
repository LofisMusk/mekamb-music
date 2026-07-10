from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import library_service, require_token
from app.api.schemas import (
    LibraryCreateRequest,
    LibraryDetailResponse,
    LibraryListResponse,
    LibraryTrackAddRequest,
    LibraryUpdateRequest,
)
from app.libraries.domain import (
    LibraryNotFound,
    LibraryTrackNotFound,
    TrackNotFound,
)
from app.libraries.service import LibraryService

router = APIRouter(dependencies=[Depends(require_token)])


@router.get("", response_model=LibraryListResponse)
async def list_libraries(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: LibraryService = Depends(library_service),
) -> LibraryListResponse:
    libraries = await service.list_libraries(limit=limit, offset=offset)
    return LibraryListResponse(
        items=[library.to_dict() for library in libraries],
        limit=limit,
        offset=offset,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=LibraryDetailResponse)
async def create_library(
    payload: LibraryCreateRequest,
    service: LibraryService = Depends(library_service),
) -> LibraryDetailResponse:
    library = await service.create_library(name=payload.name)
    return LibraryDetailResponse(**library.to_dict())


@router.get("/{library_id}", response_model=LibraryDetailResponse)
async def get_library(
    library_id: UUID,
    service: LibraryService = Depends(library_service),
) -> LibraryDetailResponse:
    try:
        library = await service.get_library(library_id)
    except LibraryNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return LibraryDetailResponse(**library.to_dict())


@router.get("/{library_id}/tracks", response_model=LibraryDetailResponse)
async def get_library_tracks(
    library_id: UUID,
    service: LibraryService = Depends(library_service),
) -> LibraryDetailResponse:
    try:
        library = await service.get_library(library_id)
    except LibraryNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return LibraryDetailResponse(**library.to_dict())


@router.patch("/{library_id}", response_model=LibraryDetailResponse)
async def update_library(
    library_id: UUID,
    payload: LibraryUpdateRequest,
    service: LibraryService = Depends(library_service),
) -> LibraryDetailResponse:
    try:
        library = await service.update_library(library_id=library_id, name=payload.name)
    except LibraryNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return LibraryDetailResponse(**library.to_dict())


@router.delete("/{library_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_library(
    library_id: UUID,
    service: LibraryService = Depends(library_service),
) -> None:
    try:
        await service.delete_library(library_id)
    except LibraryNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{library_id}/tracks", response_model=LibraryDetailResponse)
async def add_library_track(
    library_id: UUID,
    payload: LibraryTrackAddRequest,
    service: LibraryService = Depends(library_service),
) -> LibraryDetailResponse:
    try:
        library = await service.add_track(library_id=library_id, track_id=payload.track_id)
    except (LibraryNotFound, TrackNotFound) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return LibraryDetailResponse(**library.to_dict())


@router.delete("/{library_id}/tracks/{track_id}", response_model=LibraryDetailResponse)
async def remove_library_track(
    library_id: UUID,
    track_id: UUID,
    service: LibraryService = Depends(library_service),
) -> LibraryDetailResponse:
    try:
        library = await service.remove_track(library_id=library_id, track_id=track_id)
    except (LibraryNotFound, LibraryTrackNotFound) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return LibraryDetailResponse(**library.to_dict())
