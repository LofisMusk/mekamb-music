from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import playlist_service, require_token
from app.api.schemas import (
    PlaylistCreateRequest,
    PlaylistDetailResponse,
    PlaylistListResponse,
    PlaylistTrackAddRequest,
    PlaylistTrackOrderRequest,
    PlaylistUpdateRequest,
)
from app.playlists.domain import (
    PlaylistNotFound,
    PlaylistOrderMismatch,
    PlaylistTrackNotFound,
    TrackNotFound,
)
from app.playlists.service import PlaylistService

router = APIRouter(dependencies=[Depends(require_token)])


@router.get("", response_model=PlaylistListResponse)
async def list_playlists(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: PlaylistService = Depends(playlist_service),
) -> PlaylistListResponse:
    playlists = await service.list_playlists(limit=limit, offset=offset)
    return PlaylistListResponse(
        items=[playlist.to_dict() for playlist in playlists],
        limit=limit,
        offset=offset,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=PlaylistDetailResponse)
async def create_playlist(
    payload: PlaylistCreateRequest,
    service: PlaylistService = Depends(playlist_service),
) -> PlaylistDetailResponse:
    playlist = await service.create_playlist(name=payload.name)
    return PlaylistDetailResponse(**playlist.to_dict())


@router.get("/{playlist_id}", response_model=PlaylistDetailResponse)
async def get_playlist(
    playlist_id: UUID,
    service: PlaylistService = Depends(playlist_service),
) -> PlaylistDetailResponse:
    try:
        playlist = await service.get_playlist(playlist_id)
    except PlaylistNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return PlaylistDetailResponse(**playlist.to_dict())


@router.patch("/{playlist_id}", response_model=PlaylistDetailResponse)
async def update_playlist(
    playlist_id: UUID,
    payload: PlaylistUpdateRequest,
    service: PlaylistService = Depends(playlist_service),
) -> PlaylistDetailResponse:
    try:
        playlist = await service.update_playlist(playlist_id=playlist_id, name=payload.name)
    except PlaylistNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return PlaylistDetailResponse(**playlist.to_dict())


@router.delete("/{playlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_playlist(
    playlist_id: UUID,
    service: PlaylistService = Depends(playlist_service),
) -> None:
    try:
        await service.delete_playlist(playlist_id)
    except PlaylistNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{playlist_id}/tracks", response_model=PlaylistDetailResponse)
async def add_playlist_track(
    playlist_id: UUID,
    payload: PlaylistTrackAddRequest,
    service: PlaylistService = Depends(playlist_service),
) -> PlaylistDetailResponse:
    try:
        playlist = await service.add_track(playlist_id=playlist_id, track_id=payload.track_id)
    except (PlaylistNotFound, TrackNotFound) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return PlaylistDetailResponse(**playlist.to_dict())


@router.put("/{playlist_id}/tracks/order", response_model=PlaylistDetailResponse)
async def reorder_playlist_tracks(
    playlist_id: UUID,
    payload: PlaylistTrackOrderRequest,
    service: PlaylistService = Depends(playlist_service),
) -> PlaylistDetailResponse:
    try:
        playlist = await service.reorder_tracks(
            playlist_id=playlist_id,
            track_ids=payload.track_ids,
        )
    except PlaylistNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PlaylistOrderMismatch as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PlaylistDetailResponse(**playlist.to_dict())


@router.delete("/{playlist_id}/tracks/{track_id}", response_model=PlaylistDetailResponse)
async def remove_playlist_track(
    playlist_id: UUID,
    track_id: UUID,
    service: PlaylistService = Depends(playlist_service),
) -> PlaylistDetailResponse:
    try:
        playlist = await service.remove_track(playlist_id=playlist_id, track_id=track_id)
    except (PlaylistNotFound, PlaylistTrackNotFound) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return PlaylistDetailResponse(**playlist.to_dict())
