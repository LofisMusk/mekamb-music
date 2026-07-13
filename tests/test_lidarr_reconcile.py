from app.imports import lidarr_reconcile


def test_foreign_key_prefers_foreign_album_id():
    assert lidarr_reconcile._foreign_key({"id": 40, "foreignAlbumId": "mb-123"}) == "lidarr:mb-123"


def test_foreign_key_falls_back_to_lidarr_id():
    assert lidarr_reconcile._foreign_key({"id": 40}) == "lidarr:40"


def test_album_name_combines_artist_and_title():
    album = {"title": "Europa", "artist": {"artistName": "Taco Hemingway"}}
    assert lidarr_reconcile._album_name(album) == "Taco Hemingway - Europa"


def test_album_name_handles_missing_artist():
    assert lidarr_reconcile._album_name({"title": "Europa"}) == "Europa"
