import httpx
import pytest

from app.workers.ia_direct_fetch_worker import (
    TorrentParseError,
    parse_torrent,
    process_torrent,
    run_ia_blackhole_once,
    select_wanted_files,
)


def _bencode_str(s: str) -> bytes:
    b = s.encode("utf-8")
    return str(len(b)).encode() + b":" + b


def _multi_file_torrent(name: str, files: list[tuple[str, int]]) -> bytes:
    files_bytes = b""
    for path, length in files:
        parts = path.split("/")
        path_list = b"l" + b"".join(_bencode_str(p) for p in parts) + b"e"
        files_bytes += b"d4:path" + path_list + b"6:lengthi" + str(length).encode() + b"ee"
    return b"d4:infod4:name" + _bencode_str(name) + b"5:filesl" + files_bytes + b"eee"


def _single_file_torrent(name: str, length: int) -> bytes:
    return b"d4:infod4:name" + _bencode_str(name) + b"6:lengthi" + str(length).encode() + b"eee"


def test_parse_torrent_multi_file():
    data = _multi_file_torrent(
        "some-album",
        [("track1.mp3", 1000), ("track1.flac", 5000), ("cover.png", 200)],
    )
    identifier, files = parse_torrent(data)
    assert identifier == "some-album"
    assert ("track1.mp3", 1000) in files
    assert ("cover.png", 200) in files


def test_parse_torrent_single_file():
    data = _single_file_torrent("solo-track.mp3", 12345)
    identifier, files = parse_torrent(data)
    assert identifier == "solo-track.mp3"
    assert files == [("solo-track.mp3", 12345)]


def test_parse_torrent_rejects_garbage():
    with pytest.raises(TorrentParseError):
        parse_torrent(b"not bencode at all")


def test_parse_torrent_rejects_missing_info():
    with pytest.raises(TorrentParseError):
        parse_torrent(b"d4:spam4:eggse")


def test_select_wanted_files_prefers_mp3():
    files = [("a.mp3", 1000), ("a.flac", 5000), ("cover.png", 200), ("meta.xml", 50)]
    assert select_wanted_files(files) == [("a.mp3", 1000)]


def test_select_wanted_files_falls_back_to_largest_group_without_mp3():
    files = [("a.flac", 5000), ("b.flac", 5000), ("a.ogg", 2000), ("cover.png", 200)]
    wanted = select_wanted_files(files)
    assert wanted == [("a.flac", 5000), ("b.flac", 5000)]


def test_select_wanted_files_empty_when_no_audio():
    assert select_wanted_files([("cover.png", 200), ("meta.xml", 50)]) == []


class _FakeStreamResponse:
    def __init__(self, body: bytes, status_error: bool = False):
        self._body = body
        self._status_error = status_error

    def raise_for_status(self):
        if self._status_error:
            raise httpx.HTTPStatusError("error", request=None, response=None)

    async def aiter_bytes(self):
        yield self._body


class _FakeStreamContext:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self._response

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
        return _FakeStreamContext(_FakeStreamResponse(b"fake mp3 bytes"))


@pytest.mark.asyncio
async def test_process_torrent_downloads_wanted_file_and_cleans_up(tmp_path, monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    torrent_path = tmp_path / "album.torrent"
    torrent_path.write_bytes(_multi_file_torrent("album", [("song.mp3", 14), ("song.flac", 999)]))
    watch_dir = tmp_path / "watch"

    result = await process_torrent(torrent_path, watch_dir)

    assert result is True
    assert not torrent_path.exists()
    written = watch_dir / "album" / "song.mp3"
    assert written.exists()
    assert written.read_bytes() == b"fake mp3 bytes"
    assert not (watch_dir / "album" / "song.flac").exists()


@pytest.mark.asyncio
async def test_process_torrent_names_output_folder_after_torrent_file_not_identifier(tmp_path, monkeypatch):
    """Lidarr correlates a completed Blackhole download by the .torrent
    file's own name, not the archive.org identifier embedded inside it —
    these are frequently different strings, so the output folder must be
    named after the dropped .torrent file, not the parsed identifier."""
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    torrent_path = tmp_path / "Taco Hemingway – Marmur.torrent"
    torrent_path.write_bytes(
        _multi_file_torrent("taco-hemingway-marmur_202407", [("01 - Marmur.mp3", 14)])
    )
    watch_dir = tmp_path / "watch"

    result = await process_torrent(torrent_path, watch_dir)

    assert result is True
    assert (watch_dir / "Taco Hemingway – Marmur" / "01 - Marmur.mp3").exists()
    assert not (watch_dir / "taco-hemingway-marmur_202407").exists()


@pytest.mark.asyncio
async def test_process_torrent_skips_already_complete_output(tmp_path, monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("should not download when already complete")

    monkeypatch.setattr(httpx, "AsyncClient", fail_if_called)

    torrent_path = tmp_path / "album.torrent"
    torrent_path.write_bytes(_multi_file_torrent("album", [("song.mp3", 4)]))
    watch_dir = tmp_path / "watch"
    output = watch_dir / "album" / "song.mp3"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"done")  # exactly 4 bytes, matching declared size

    result = await process_torrent(torrent_path, watch_dir)

    assert result is True
    assert not torrent_path.exists()


@pytest.mark.asyncio
async def test_process_torrent_no_audio_files_leaves_torrent_for_retry(tmp_path):
    torrent_path = tmp_path / "junk.torrent"
    torrent_path.write_bytes(_multi_file_torrent("junk", [("cover.png", 10)]))
    watch_dir = tmp_path / "watch"

    result = await process_torrent(torrent_path, watch_dir)

    assert result is False
    assert torrent_path.exists()


@pytest.mark.asyncio
async def test_run_ia_blackhole_once_processes_all_pending_torrents(tmp_path, monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    from app.core.config import settings

    torrent_dir = tmp_path / "torrents"
    watch_dir = tmp_path / "watch"
    torrent_dir.mkdir()
    (torrent_dir / "a.torrent").write_bytes(_multi_file_torrent("album-a", [("x.mp3", 14)]))
    (torrent_dir / "b.torrent").write_bytes(_multi_file_torrent("album-b", [("y.mp3", 14)]))

    monkeypatch.setattr(settings, "ia_blackhole_torrent_dir", torrent_dir)
    monkeypatch.setattr(settings, "ia_blackhole_watch_dir", watch_dir)

    processed = await run_ia_blackhole_once()

    assert processed == 2
    assert (watch_dir / "a" / "x.mp3").exists()
    assert (watch_dir / "b" / "y.mp3").exists()
