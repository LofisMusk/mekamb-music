import io
import zipfile

import httpx
import pytest

from app.workers.ia_backfill_worker import _import_into_lidarr, _process_album


def _album_zip() -> bytes:
    """A /compress/-style zip: two mp3s plus a cover that must be filtered out."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("01.mp3", b"fake audio one")
        zf.writestr("02.mp3", b"fake audio two")
        zf.writestr("cover.png", b"not audio")
    return buf.getvalue()


class _FakeStreamResponse:
    def __init__(self, body: bytes):
        self._body = body

    def raise_for_status(self):
        pass

    async def aiter_bytes(self):
        yield self._body


class _FakeStreamContext:
    def __init__(self, body: bytes):
        self._body = body

    async def __aenter__(self):
        return _FakeStreamResponse(self._body)

    async def __aexit__(self, *args):
        return False


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def stream(self, method, url):
        return _FakeStreamContext(_album_zip())


class FakeIa:
    def __init__(self, docs, formats):
        self._docs = docs
        self._formats = formats

    async def search_audio_items(self, artist, album, *, rows=25):
        return self._docs

    async def item_formats(self, identifier):
        return self._formats


class FakeLidarr:
    def __init__(self, *, release_id=211):
        self._release_id = release_id
        self.imported = None
        self.scoped = None
        self.tracks_release = None

    def get_album(self, album_id):
        return {"releases": [{"id": self._release_id, "monitored": True}]}

    def album_tracks(self, *, album_release_id):
        self.tracks_release = album_release_id
        return [
            {"id": 11, "trackNumber": "1", "mediumNumber": 1},
            {"id": 12, "trackNumber": "2", "mediumNumber": 1},
        ]

    def manual_import_candidates(self, folder, *, artist_id, album_id):
        import os

        self.scoped = (artist_id, album_id)
        # Mirrors the real failure mode: Lidarr parses quality but maps no album.
        return [
            {"path": os.path.join(folder, name), "quality": {"quality": {"id": 8, "name": "MP3-256"}},
             "albumReleaseId": 0, "tracks": [], "rejections": [{"reason": "Couldn't find similar album"}]}
            for name in ("01.mp3", "02.mp3")
        ]

    def run_manual_import(self, files, *, import_mode="move"):
        self.imported = (files, import_mode)
        return {"id": 1}


def test_import_into_lidarr_forces_target_ids(tmp_path):
    album = {"id": 9}
    lidarr = FakeLidarr()
    album_dir = tmp_path / "Taco Hemingway - Marmur"
    album_dir.mkdir()
    (album_dir / "01.mp3").write_bytes(b"x")
    (album_dir / "02.mp3").write_bytes(b"x")

    count = _import_into_lidarr(lidarr, album=album, artist_id=5, album_dir=album_dir)

    assert count == 2
    assert lidarr.scoped == (5, 9)  # scan scoped to the target artist+album
    files, mode = lidarr.imported
    assert all(f["albumId"] == 9 and f["artistId"] == 5 and f["albumReleaseId"] == 211 for f in files)
    assert [f["trackIds"] for f in files] == [[11], [12]]


@pytest.mark.asyncio
async def test_process_album_downloads_and_imports(tmp_path, monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    from app.core.config import settings

    monkeypatch.setattr(settings, "ia_backfill_staging_dir", tmp_path)
    monkeypatch.setattr(settings, "ia_backfill_min_match_score", 0.6)

    ia = FakeIa(
        docs=[{"identifier": "taco-hemingway-marmur_202405", "title": "Taco Hemingway – Marmur (MP3)", "downloads": 300}],
        formats=["PNG", "VBR MP3", "Spectrogram"],
    )
    lidarr = FakeLidarr()
    album = {"id": 9, "title": "Marmur", "artistId": 5, "artist": {"artistName": "Taco Hemingway", "id": 5}}

    ok = await _process_album(album, ia, lidarr)

    assert ok is True
    assert (tmp_path / "Taco Hemingway - Marmur" / "01.mp3").read_bytes() == b"fake audio one"
    assert not (tmp_path / "Taco Hemingway - Marmur" / "cover.png").exists()  # non-audio filtered from zip
    assert lidarr.imported is not None


@pytest.mark.asyncio
async def test_process_album_skips_when_no_match(tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ia_backfill_staging_dir", tmp_path)
    ia = FakeIa(docs=[{"identifier": "unrelated", "title": "Something Else Entirely"}], formats=[])
    lidarr = FakeLidarr()
    album = {"id": 9, "title": "Marmur", "artistId": 5, "artist": {"artistName": "Taco Hemingway", "id": 5}}

    assert await _process_album(album, ia, lidarr) is False
    assert lidarr.imported is None
