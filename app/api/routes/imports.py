from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import import_service, personal_1337x_provider, require_token
from app.api.schemas import ImportListResponse, ImportRecordResponse
from app.imports.domain import ImportNotFound
from app.imports.service import ImportService, InvalidImportCandidate, SandboxViolation
from app.sources.personal_1337x import (
    MissingTorrentMetadata,
    OwnershipMismatch,
    Personal1337xProvider,
    ProviderDisabledError,
)

router = APIRouter(dependencies=[Depends(require_token)])


@router.get("", response_model=ImportListResponse)
async def list_imports(
    status_filter: str | None = Query(default=None, alias="status", min_length=1, max_length=32),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: ImportService = Depends(import_service),
) -> ImportListResponse:
    records = await service.list_imports(status=status_filter, limit=limit, offset=offset)
    return ImportListResponse(
        items=[record.to_dict() for record in records],
        status=status_filter,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/1337x/{torrent_id}",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ImportRecordResponse,
)
async def import_personal_1337x(
    torrent_id: str,
    provider: Personal1337xProvider = Depends(personal_1337x_provider),
    service: ImportService = Depends(import_service),
) -> ImportRecordResponse:
    try:
        candidate = await provider.resolve_for_import(torrent_id)
        record = await service.create_1337x_import(candidate)
    except ProviderDisabledError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except OwnershipMismatch as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except (MissingTorrentMetadata, InvalidImportCandidate, SandboxViolation) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return ImportRecordResponse(**record.to_dict())


@router.get("/{import_id}", response_model=ImportRecordResponse)
async def get_import(
    import_id: UUID,
    service: ImportService = Depends(import_service),
) -> ImportRecordResponse:
    try:
        record = await service.get_import(import_id)
    except ImportNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ImportRecordResponse(**record.to_dict())


@router.post("/{import_id}/cancel", response_model=ImportRecordResponse)
async def cancel_import(
    import_id: UUID,
    delete_files: bool = Query(default=True),
    service: ImportService = Depends(import_service),
) -> ImportRecordResponse:
    try:
        record = await service.cancel_import(import_id, delete_files=delete_files)
    except ImportNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SandboxViolation as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ImportRecordResponse(**record.to_dict())
