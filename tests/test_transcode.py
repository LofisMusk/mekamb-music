from pathlib import Path
from uuid import uuid4

import pytest

from app.api.routes import tracks as tracks_module
from app.library.transcode import (
    TranscodeUnavailable,
    is_lossless_source,
    transcode_to_aac,
)


def test_is_lossless_source_by_extension():
    assert is_lossless_source(Path("song.flac"), None)
    assert is_lossless_source(Path("song.wav"), None)
    assert is_lossless_source(Path("song.aiff"), None)
    assert not is_lossless_source(Path("song.mp3"), None)
    assert not is_lossless_source(Path("song.m4a"), None)


def test_is_lossless_source_by_media_type():
    assert is_lossless_source(Path("blob"), "audio/flac")
    assert is_lossless_source(Path("blob"), "audio/x-flac")
    assert not is_lossless_source(Path("blob"), "audio/mpeg")
    assert not is_lossless_source(Path("blob"), "audio/aac")


def test_transcode_returns_existing_cache_hit_without_ffmpeg(tmp_path):
    # A non-empty cached .m4a is returned directly, so ffmpeg is never invoked.
    cache = tmp_path / "transcode"
    cache.mkdir()
    cached = cache / "track-123.m4a"
    cached.write_bytes(b"already transcoded")

    result = transcode_to_aac(
        Path("/does/not/matter.flac"),
        track_id="track-123",
        cache_root=cache,
        bitrate="256k",
    )
    assert result == cached


def test_transcode_raises_when_ffmpeg_missing(monkeypatch, tmp_path):
    monkeypatch.setattr("app.library.transcode.shutil.which", lambda _name: None)
    with pytest.raises(TranscodeUnavailable):
        transcode_to_aac(
            tmp_path / "source.flac",
            track_id="track-x",
            cache_root=tmp_path / "cache",
            bitrate="256k",
        )


class _FakeStorage:
    def __init__(self, path):
        self._path = path

    def ensure_cached(self, _key):
        return self._path


class _FakeTrack:
    def __init__(self, media_type):
        self.media_type = media_type
        self.storage_key = "abc/song"


class _FakeSession:
    def __init__(self, track):
        self._track = track

    async def get(self, _model, _track_id):
        return self._track


@pytest.mark.asyncio
async def test_resolve_stream_target_transcodes_lossless(monkeypatch, tmp_path):
    src = tmp_path / "song.flac"
    src.write_bytes(b"flac-bytes")
    aac = tmp_path / "song.m4a"
    aac.write_bytes(b"aac-bytes")
    monkeypatch.setattr(tracks_module, "build_library_storage", lambda _s: _FakeStorage(src))
    monkeypatch.setattr(tracks_module, "transcode_to_aac", lambda *a, **k: aac)

    track, path, media_type, size = await tracks_module._resolve_stream_target(
        uuid4(), _FakeSession(_FakeTrack("audio/flac")), want_aac=True
    )
    assert path == aac
    assert media_type == "audio/mp4"
    assert size == aac.stat().st_size


@pytest.mark.asyncio
async def test_resolve_stream_target_serves_original_when_lossy(monkeypatch, tmp_path):
    src = tmp_path / "song.mp3"
    src.write_bytes(b"mp3-bytes")
    monkeypatch.setattr(tracks_module, "build_library_storage", lambda _s: _FakeStorage(src))

    def _boom(*_a, **_k):
        raise AssertionError("lossy sources must not be transcoded")

    monkeypatch.setattr(tracks_module, "transcode_to_aac", _boom)

    _, path, media_type, _ = await tracks_module._resolve_stream_target(
        uuid4(), _FakeSession(_FakeTrack("audio/mpeg")), want_aac=True
    )
    assert path == src
    assert media_type == "audio/mpeg"
