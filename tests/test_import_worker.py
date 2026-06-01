from pathlib import Path
from uuid import uuid4

import pytest

from app.core.config import settings
from app.db.models import ImportJob, Track
from app.downloads.domain import TorrentRuntimeStatus
from app.storage.local import LocalStorage
from app.workers.import_worker import process_downloaded_job_safely, process_job


@pytest.fixture(autouse=True)
def quarantine_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "quarantine_root", tmp_path / "quarantine")


class FakeSession:
    def __init__(self):
        self.added = []

    def add(self, item):
        self.added.append(item)


class FakeTorrentClient:
    def __init__(self, status):
        self.status = status
        self.labels = []

    async def status_by_label(self, label: str):
        self.labels.append(label)
        return self.status


class FailingTorrentClient:
    async def status_by_label(self, label: str):
        raise RuntimeError("torrent client unavailable")


def torrent_status(
    *,
    progress: float,
    state: str = "downloading",
    info_hash: str = "ABC123",
    save_path: str = "/downloads/incomplete/import-1",
) -> TorrentRuntimeStatus:
    return TorrentRuntimeStatus(
        name="track.mp3",
        info_hash=info_hash,
        state=state,
        progress=progress,
        size_bytes=100,
        downloaded_bytes=int(100 * progress),
        download_speed_bytes=1,
        eta_seconds=10,
        save_path=save_path,
    )


@pytest.mark.asyncio
async def test_worker_imports_only_audio_files_from_quarantine(tmp_path: Path):
    quarantine = tmp_path / "quarantine" / "import-1"
    library = tmp_path / "library"
    quarantine.mkdir(parents=True)
    (quarantine / "track.mp3").write_bytes(b"fake mp3 bytes")
    (quarantine / "notes.txt").write_text("not audio")

    job = ImportJob(
        torrent_id="1",
        info_hash="ABC123",
        magnet_link="magnet:?xt=urn:btih:ABC123",
        uploader="mekamb",
        source_url="https://1337x.to/torrent/1/mine/",
        status="queued",
        quarantine_path=str(quarantine),
    )
    session = FakeSession()

    await process_job(job, session, LocalStorage(library))

    assert job.status == "imported"
    assert len(session.added) == 1
    assert isinstance(session.added[0], Track)
    assert session.added[0].original_filename == "track.mp3"
    assert not any(path.name == "notes.txt" for path in library.rglob("*"))
    assert list(library.rglob("*.mp3"))
    assert not (quarantine / "notes.txt").exists()
    assert (quarantine / "track.mp3").exists()


@pytest.mark.asyncio
async def test_worker_does_not_import_until_torrent_is_complete(tmp_path: Path):
    quarantine = tmp_path / "quarantine" / "import-1"
    library = tmp_path / "library"
    quarantine.mkdir(parents=True)
    (quarantine / "track.mp3").write_bytes(b"partial bytes")
    job_id = uuid4()
    job = ImportJob(
        id=job_id,
        torrent_id="1",
        info_hash="ABC123",
        magnet_link="magnet:?xt=urn:btih:ABC123",
        uploader="mekamb",
        source_url="https://1337x.to/torrent/1/mine/",
        status="queued",
        quarantine_path=str(quarantine),
    )
    session = FakeSession()
    torrent_client = FakeTorrentClient(torrent_status(progress=0.25))

    await process_downloaded_job_safely(job, session, LocalStorage(library), torrent_client)

    assert torrent_client.labels == [f"mekamb-music:{job_id}"]
    assert job.status == "downloading"
    assert session.added == []
    assert not library.exists()


@pytest.mark.asyncio
async def test_worker_imports_after_torrent_is_complete(tmp_path: Path):
    quarantine = tmp_path / "quarantine" / "import-1"
    library = tmp_path / "library"
    quarantine.mkdir(parents=True)
    (quarantine / "track.mp3").write_bytes(b"complete bytes")
    job = ImportJob(
        id=uuid4(),
        torrent_id="1",
        info_hash="ABC123",
        magnet_link="magnet:?xt=urn:btih:ABC123",
        uploader="mekamb",
        source_url="https://1337x.to/torrent/1/mine/",
        status="downloading",
        quarantine_path=str(quarantine),
    )
    session = FakeSession()

    await process_downloaded_job_safely(
        job,
        session,
        LocalStorage(library),
        FakeTorrentClient(
            torrent_status(
                progress=1.0,
                state="uploading",
                save_path=f"/downloads/incomplete/{job.id}",
            )
        ),
    )

    assert job.status == "imported"
    assert len(session.added) == 1
    assert list(library.rglob("*.mp3"))


@pytest.mark.asyncio
async def test_worker_fails_completed_torrent_with_mismatched_info_hash(tmp_path: Path):
    quarantine = tmp_path / "quarantine" / "import-1"
    library = tmp_path / "library"
    quarantine.mkdir(parents=True)
    (quarantine / "track.mp3").write_bytes(b"complete bytes")
    job = ImportJob(
        id=uuid4(),
        torrent_id="1",
        info_hash="ABC123",
        magnet_link="magnet:?xt=urn:btih:ABC123",
        uploader="mekamb",
        source_url="https://1337x.to/torrent/1/mine/",
        status="downloading",
        quarantine_path=str(quarantine),
    )
    session = FakeSession()

    await process_downloaded_job_safely(
        job,
        session,
        LocalStorage(library),
        FakeTorrentClient(
            torrent_status(
                progress=1.0,
                state="uploading",
                info_hash="OTHER",
                save_path=f"/downloads/incomplete/{job.id}",
            )
        ),
    )

    assert job.status == "failed"
    assert "does not match import" in job.error_message
    assert session.added == []
    assert not library.exists()


@pytest.mark.asyncio
async def test_worker_fails_completed_torrent_with_mismatched_save_path(tmp_path: Path):
    quarantine = tmp_path / "quarantine" / "import-1"
    library = tmp_path / "library"
    quarantine.mkdir(parents=True)
    (quarantine / "track.mp3").write_bytes(b"complete bytes")
    job = ImportJob(
        id=uuid4(),
        torrent_id="1",
        info_hash="ABC123",
        magnet_link="magnet:?xt=urn:btih:ABC123",
        uploader="mekamb",
        source_url="https://1337x.to/torrent/1/mine/",
        status="downloading",
        quarantine_path=str(quarantine),
    )
    session = FakeSession()

    await process_downloaded_job_safely(
        job,
        session,
        LocalStorage(library),
        FakeTorrentClient(
            torrent_status(
                progress=1.0,
                state="uploading",
                save_path="/downloads/incomplete/some-other-import",
            )
        ),
    )

    assert job.status == "failed"
    assert "save_path" in job.error_message
    assert session.added == []
    assert not library.exists()


@pytest.mark.asyncio
async def test_worker_keeps_job_queued_when_torrent_is_not_visible(tmp_path: Path):
    quarantine = tmp_path / "quarantine" / "import-1"
    quarantine.mkdir(parents=True)
    job = ImportJob(
        id=uuid4(),
        torrent_id="1",
        info_hash="ABC123",
        magnet_link="magnet:?xt=urn:btih:ABC123",
        uploader="mekamb",
        source_url="https://1337x.to/torrent/1/mine/",
        status="queued",
        quarantine_path=str(quarantine),
    )
    session = FakeSession()

    await process_downloaded_job_safely(job, session, LocalStorage(tmp_path / "library"), FakeTorrentClient(None))

    assert job.status == "queued"
    assert "not visible" in job.error_message
    assert session.added == []


@pytest.mark.asyncio
async def test_worker_keeps_job_active_when_torrent_client_is_unavailable(tmp_path: Path):
    quarantine = tmp_path / "quarantine" / "import-1"
    quarantine.mkdir(parents=True)
    job = ImportJob(
        id=uuid4(),
        torrent_id="1",
        info_hash="ABC123",
        magnet_link="magnet:?xt=urn:btih:ABC123",
        uploader="mekamb",
        source_url="https://1337x.to/torrent/1/mine/",
        status="downloading",
        quarantine_path=str(quarantine),
    )
    session = FakeSession()

    await process_downloaded_job_safely(
        job,
        session,
        LocalStorage(tmp_path / "library"),
        FailingTorrentClient(),
    )

    assert job.status == "downloading"
    assert "torrent client unavailable" in job.error_message
    assert session.added == []
