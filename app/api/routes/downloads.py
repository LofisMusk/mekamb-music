from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from httpx import HTTPError

from app.api.deps import download_service, require_token
from app.api.schemas import DownloadStatusResponse
from app.downloads.qbittorrent import QBittorrentError
from app.downloads.service import DownloadService
from app.imports.domain import ImportNotFound

router = APIRouter(dependencies=[Depends(require_token)])


@router.get("/{import_id}", response_model=DownloadStatusResponse)
async def get_download(
    import_id: UUID,
    service: DownloadService = Depends(download_service),
) -> DownloadStatusResponse:
    try:
        status_payload = await service.get_download_status(import_id)
    except ImportNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (HTTPError, QBittorrentError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not read torrent client status: {exc}",
        ) from exc

    return DownloadStatusResponse(**status_payload.to_dict())
