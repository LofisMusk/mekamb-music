import pytest

from app.core.config import settings
from app.db.models import ImportJob
from app.workers.import_worker import process_job_safely


@pytest.fixture(autouse=True)
def quarantine_root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "quarantine_root", tmp_path / "quarantine")


class FakeSession:
    def add(self, item):
        raise AssertionError("failed jobs should not add tracks")


class RecordingSession:
    def __init__(self):
        self.added = []

    def add(self, item):
        self.added.append(item)


class FailingStorage:
    def put_file(self, source, key):
        raise RuntimeError("storage unavailable")


class FailingSecondStorage:
    def __init__(self):
        self.keys = []

    def put_file(self, source, key):
        self.keys.append(key)
        if len(self.keys) == 2:
            raise RuntimeError("second file failed")
        return key


@pytest.mark.asyncio
async def test_worker_marks_job_failed_when_storage_fails(tmp_path):
    quarantine = tmp_path / "quarantine" / "import-1"
    quarantine.mkdir(parents=True)
    (quarantine / "track.mp3").write_bytes(b"fake audio")
    job = ImportJob(
        torrent_id="1",
        info_hash="ABC123",
        magnet_link="magnet:?xt=urn:btih:ABC123",
        uploader="mekamb",
        source_url="https://1337x.to/torrent/1/mine/",
        status="queued",
        quarantine_path=str(quarantine),
    )

    await process_job_safely(job, FakeSession(), FailingStorage())

    assert job.status == "failed"
    assert job.error_message == "storage unavailable"


@pytest.mark.asyncio
async def test_worker_does_not_add_partial_track_records_when_later_file_fails(tmp_path):
    quarantine = tmp_path / "quarantine" / "import-1"
    quarantine.mkdir(parents=True)
    (quarantine / "01-track.mp3").write_bytes(b"first audio")
    (quarantine / "02-track.mp3").write_bytes(b"second audio")
    job = ImportJob(
        torrent_id="1",
        info_hash="ABC123",
        magnet_link="magnet:?xt=urn:btih:ABC123",
        uploader="mekamb",
        source_url="https://1337x.to/torrent/1/mine/",
        status="queued",
        quarantine_path=str(quarantine),
    )
    session = RecordingSession()
    storage = FailingSecondStorage()

    await process_job_safely(job, session, storage)

    assert job.status == "failed"
    assert job.error_message == "second file failed"
    assert len(storage.keys) == 2
    assert session.added == []
