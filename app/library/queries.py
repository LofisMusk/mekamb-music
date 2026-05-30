from sqlalchemy import Select, func, or_, select

from app.db.models import Track


def build_track_list_query(*, q: str | None, limit: int, offset: int) -> Select[tuple[Track]]:
    statement = select(Track)
    normalized_query = q.strip() if q else ""
    if normalized_query:
        pattern = f"%{normalized_query}%"
        statement = statement.where(
            or_(
                Track.title.ilike(pattern),
                Track.artist.ilike(pattern),
                Track.album.ilike(pattern),
                Track.original_filename.ilike(pattern),
            )
        )

    return statement.order_by(Track.created_at.desc()).limit(limit).offset(offset)


def build_artist_list_query(*, q: str | None, limit: int, offset: int):
    artist_name = func.coalesce(Track.artist, "Unknown Artist").label("name")
    normalized_query = q.strip() if q else ""
    statement = (
        select(
            artist_name,
            func.count(Track.id).label("track_count"),
            func.max(Track.created_at).label("latest_track_at"),
        )
        .group_by(artist_name)
        .order_by(artist_name.asc())
        .limit(limit)
        .offset(offset)
    )
    if normalized_query:
        statement = statement.where(Track.artist.ilike(f"%{normalized_query}%"))
    return statement


def build_album_list_query(*, q: str | None, limit: int, offset: int):
    artist_name = func.coalesce(Track.artist, "Unknown Artist").label("artist")
    album_title = func.coalesce(Track.album, "Unknown Album").label("title")
    normalized_query = q.strip() if q else ""
    statement = (
        select(
            album_title,
            artist_name,
            func.count(Track.id).label("track_count"),
            func.max(Track.created_at).label("latest_track_at"),
        )
        .group_by(album_title, artist_name)
        .order_by(artist_name.asc(), album_title.asc())
        .limit(limit)
        .offset(offset)
    )
    if normalized_query:
        pattern = f"%{normalized_query}%"
        statement = statement.where(or_(Track.album.ilike(pattern), Track.artist.ilike(pattern)))
    return statement


def row_mapping(row: object) -> dict[str, object]:
    mapping = getattr(row, "_mapping", row)
    return dict(mapping)
