import asyncio
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from urllib.parse import quote
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import db_session, import_service, require_token
from app.api.schemas import (
    SyncActionListResponse,
    SyncActionPushRequest,
    SyncActionPushResponse,
    SyncActionResponse,
    SyncApplyResponse,
    SyncImportManifestResponse,
)
from app.core.auth import ApiKeyIdentity
from app.core.config import settings
from app.db.models import ImportJob, Track, UserAction
from app.imports.service import ImportService
from app.library.audio import media_type_for_audio_file
from app.storage.library import build_library_storage
from app.sync.actions import apply_action, apply_actions_batch, bulk_merge_remote_actions, list_actions

router = APIRouter(dependencies=[Depends(require_token)])


@router.get("/actions", response_model=SyncActionListResponse)
async def get_sync_actions(
    since: datetime | None = Query(default=None),
    include_applied: bool = Query(default=True),
    limit: int = Query(default=200, ge=1, le=1000),
    api_key: ApiKeyIdentity = Depends(require_token),
    session: AsyncSession = Depends(db_session),
) -> SyncActionListResponse:
    actions = await list_actions(
        session,
        api_key_id=api_key.id,
        since=since,
        include_applied=include_applied,
        limit=limit,
    )
    return SyncActionListResponse(
        items=[SyncActionResponse(**action.to_dict()) for action in actions],
        since=since,
        include_applied=include_applied,
        limit=limit,
        offset=0,
    )


@router.post("/actions", response_model=SyncActionPushResponse)
async def push_sync_actions(
    payload: SyncActionPushRequest,
    api_key: ApiKeyIdentity = Depends(require_token),
    session: AsyncSession = Depends(db_session),
) -> SyncActionPushResponse:
    accepted, skipped = await bulk_merge_remote_actions(
        session, payload.items, api_key_id=api_key.id
    )
    return SyncActionPushResponse(accepted=accepted, skipped_existing=skipped)


@router.post("/apply", response_model=SyncApplyResponse)
async def apply_pending_sync_actions(
    limit: int = Query(default=50, ge=1, le=200),
    api_key: ApiKeyIdentity = Depends(require_token),
    session: AsyncSession = Depends(db_session),
    service: ImportService = Depends(import_service),
) -> SyncApplyResponse:
    actions = await list_actions(
        session,
        api_key_id=api_key.id,
        since=None,
        include_applied=False,
        limit=limit,
    )
    applied_items = await apply_actions_batch(session, actions, import_service=service)

    failed = sum(1 for action in applied_items if action.apply_error)
    return SyncApplyResponse(
        applied=len(applied_items) - failed,
        failed=failed,
        items=[SyncActionResponse(**action.to_dict()) for action in applied_items],
    )


@router.post("/actions/{action_id}/apply", response_model=SyncActionResponse)
async def apply_single_sync_action(
    action_id: UUID,
    api_key: ApiKeyIdentity = Depends(require_token),
    session: AsyncSession = Depends(db_session),
    service: ImportService = Depends(import_service),
) -> SyncActionResponse:
    action = await session.get(UserAction, action_id)
    if action is None or action.api_key_id != api_key.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sync action not found.")
    action = await apply_action(session, action, import_service=service)
    return SyncActionResponse(**action.to_dict())


@router.get("/imports/{info_hash}/tracks", response_model=SyncImportManifestResponse)
async def get_sync_import_manifest(
    info_hash: str,
    session: AsyncSession = Depends(db_session),
) -> SyncImportManifestResponse:
    import_record = await session.scalar(
        select(ImportJob).where(ImportJob.info_hash == info_hash).limit(1)
    )
    if import_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import not found.")

    tracks = list(
        await session.scalars(
            select(Track)
            .where(Track.source_import_id == import_record.id)
            .order_by(Track.created_at.asc(), Track.title.asc())
        )
    )
    return SyncImportManifestResponse(
        info_hash=info_hash,
        import_record=import_record.to_dict(),
        tracks=[track.to_dict() for track in tracks],
    )


@router.get("/tracks/{track_id}/file")
async def get_sync_track_file(
    track_id: UUID,
    session: AsyncSession = Depends(db_session),
) -> FileResponse:
    track = await session.get(Track, track_id)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found.")

    try:
        storage = build_library_storage(settings)
        path = await asyncio.to_thread(storage.ensure_cached, track.storage_key)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid library path.") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found.") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not prepare audio file for sync: {exc}",
        ) from exc

    media_type = track.media_type
    if not media_type or media_type == "application/octet-stream":
        media_type = media_type_for_audio_file(path)
    return FileResponse(
        path,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{track.original_filename.replace(chr(34), chr(39))}"; '
                f"filename*=UTF-8''{quote(track.original_filename)}"
            )
        },
    )
