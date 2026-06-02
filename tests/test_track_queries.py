from app.library.queries import build_album_list_query, build_artist_list_query, build_track_list_query


def test_track_list_query_supports_text_search_limit_and_offset():
    statement = build_track_list_query(q="ambient", limit=25, offset=50)
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert "ambient" in compiled
    assert "tracks.title" in compiled
    assert "tracks.artist" in compiled
    assert "tracks.album" in compiled
    assert "tracks.original_filename" in compiled
    assert "LIMIT 25" in compiled
    assert "OFFSET 50" in compiled


def test_track_list_query_without_search_only_orders_and_pages():
    statement = build_track_list_query(q="  ", limit=10, offset=0)
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert "WHERE" not in compiled
    assert "ORDER BY tracks.created_at DESC" in compiled
    assert "LIMIT 10" in compiled


def test_artist_list_query_groups_tracks_by_artist():
    statement = build_artist_list_query(q="mek", limit=20, offset=5)
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert "coalesce(tracks.artist" in compiled
    assert "count(tracks.id)" in compiled
    assert "lower(tracks.artist) LIKE lower('%mek%')" in compiled
    assert "LIMIT 20" in compiled
    assert "OFFSET 5" in compiled


def test_album_list_query_groups_tracks_by_album_only():
    statement = build_album_list_query(q="private", limit=15, offset=0)
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert "coalesce(tracks.album" in compiled
    assert "min(coalesce(tracks.artist" in compiled
    assert "GROUP BY coalesce(tracks.album" in compiled
    assert "count(tracks.id)" in compiled
    assert "lower(tracks.album) LIKE lower('%private%')" in compiled
    assert "LIMIT 15" in compiled
