from pathlib import Path

import pytest

from app.core.config import settings
from app.db.models import ImportJob, Track
from app.storage.local import LocalStorage
from app.workers.import_worker import process_job


@pytest.fixture(autouse=True)
def quarantine_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "quarantine_root", tmp_path / "quarantine")


class FakeSession:
    def __init__(self):
        self.added = []

    def add(self, item):
        self.added.append(item)


def _lidarr_job(quarantine: Path, *, info_hash: str = "lidarr:42") -> ImportJob:
    return ImportJob(
        torrent_id=info_hash,
        info_hash=info_hash,
        magnet_link="",
        uploader="lidarr",
        source_url="lidarr",
        status="ready_to_import",
        quarantine_path=str(quarantine),
        source="lidarr",
    )


@pytest.mark.asyncio
async def test_worker_imports_only_audio_files_from_quarantine(tmp_path: Path):
    quarantine = tmp_path / "quarantine" / "import-1"
    library = tmp_path / "library"
    quarantine.mkdir(parents=True)
    (quarantine / "track.mp3").write_bytes(b"fake mp3 bytes")
    (quarantine / "notes.txt").write_text("not audio")

    job = _lidarr_job(quarantine)
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
async def test_worker_uses_downloaded_cover_file_for_import_thumbnail(tmp_path: Path):
    quarantine = tmp_path / "quarantine" / "import-1"
    library = tmp_path / "library"
    quarantine.mkdir(parents=True)
    (quarantine / "track.mp3").write_bytes(b"fake mp3 bytes")
    (quarantine / "cover.jpg").write_bytes(b"cover bytes")

    job = _lidarr_job(quarantine)
    session = FakeSession()

    await process_job(job, session, LocalStorage(library))

    assert job.status == "imported"
    # The Lidarr key "lidarr:42" is normalized to a filesystem-safe namespace.
    assert session.added[0].cover_key == "lidarr_42/cover.jpg"
    assert (library / "lidarr_42" / "cover.jpg").read_bytes() == b"cover bytes"
