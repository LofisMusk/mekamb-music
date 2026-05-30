from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import personal_1337x_provider, require_token
from app.api.schemas import Source1337xSearchResponse
from app.sources.personal_1337x import Personal1337xProvider, ProviderDisabledError

router = APIRouter(dependencies=[Depends(require_token)])


@router.get("/1337x/search", response_model=Source1337xSearchResponse)
async def search_personal_1337x(
    q: str = Query(min_length=1, max_length=120),
    page: int = Query(default=1, ge=1, le=5),
    sort_by: str = Query(default="seeders", pattern="^(seeders|time)$"),
    provider: Personal1337xProvider = Depends(personal_1337x_provider),
) -> Source1337xSearchResponse:
    try:
        results = await provider.search(q, page=page, sort_by=sort_by)
    except ProviderDisabledError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return Source1337xSearchResponse(
        items=[item.to_dict() for item in results],
        filtered_by_uploader=provider.uploader,
    )
