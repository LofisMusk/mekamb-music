import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from app.imports.domain import ImportRecord
from app.imports.service import ImportService, QuarantinePlanner, SandboxViolation
from app.sources.personal_1337x import Personal1337xImportCandidate


class FakeRepository:
    def __init__(self):
        self.records = {}

    async def add(self, record: ImportRecord) -> ImportRecord:
        self.records[record.id] = record
        return record

    async def get(self, import_id: UUID) -> ImportRecord:
        return self.records[import_id]

    async def get_by_info_hash(self, info_hash: str) -> ImportRecord | None:
        for record in self.records.values():
            if record.info_hash == info_hash:
                return record
        return None

    async def list(self, *, status: str | None, limit: int, offset: int) -> list[ImportRecord]:
        records = list(self.records.values())
        if status:
            records = [record for record in records if record.status == status]
        return records[offset : offset + limit]

    async def update(self, record: ImportRecord) -> ImportRecord:
        self.records[record.id] = record
        return record


class FakeDownloader:
    def __init__(self):
        self.calls = []
        self.deletes = []
        self.delete_result = True

    async def enqueue(self, *, magnet_link: str, download_path: Path, label: str) -> None:
        self.calls.append((magnet_link, download_path, label))

    async def delete_by_label(self, label: str, *, delete_files: bool) -> bool:
        self.deletes.append((label, delete_files))
        return self.delete_result


class ImportServiceTests(unittest.IsolatedAsyncioTestCase):
    def _candidate(self, *, info_hash: str = "ABC") -> Personal1337xImportCandidate:
        return Personal1337xImportCandidate(
            torrent_id="1",
            info_hash=info_hash,
            magnet_link=f"magnet:?xt=urn:btih:{info_hash}",
            uploader="mekamb",
            source_url="https://1337x.to/torrent/1/example/",
            name="mine",
            fetched_at=datetime.now(UTC),
        )

    async def test_import_uses_quarantine_not_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repository = FakeRepository()
            downloader = FakeDownloader()
            service = ImportService(
                repository=repository,
                downloader=downloader,
                planner=QuarantinePlanner(
                    quarantine_root=root / "quarantine",
                    torrent_download_root=Path("/downloads/incomplete"),
                    library_root=root / "library",
                ),
            )

            record = await service.create_1337x_import(self._candidate())

            self.assertIn("quarantine", record.quarantine_path)
            self.assertNotIn("/library", record.quarantine_path)
            self.assertEqual(len(downloader.calls), 1)

    async def test_import_is_idempotent_by_info_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repository = FakeRepository()
            downloader = FakeDownloader()
            service = ImportService(
                repository=repository,
                downloader=downloader,
                planner=QuarantinePlanner(
                    quarantine_root=root / "quarantine",
                    torrent_download_root=Path("/downloads/incomplete"),
                    library_root=root / "library",
                ),
            )
            existing = ImportRecord(
                id=uuid4(),
                source="personal_1337x",
                torrent_id="old",
                info_hash="ABC",
                magnet_link="magnet:?xt=urn:btih:ABC",
                uploader="mekamb",
                source_url="https://1337x.to/torrent/old/example/",
                status="queued",
                quarantine_path=str(root / "quarantine" / "existing"),
                error_message=None,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            await repository.add(existing)

            record = await service.create_1337x_import(self._candidate(info_hash="ABC"))

            self.assertEqual(record.id, existing.id)
            self.assertEqual(downloader.calls, [])

    async def test_cancel_import_removes_torrent_and_quarantine_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repository = FakeRepository()
            downloader = FakeDownloader()
            service = ImportService(
                repository=repository,
                downloader=downloader,
                planner=QuarantinePlanner(
                    quarantine_root=root / "quarantine",
                    torrent_download_root=Path("/downloads/incomplete"),
                    library_root=root / "library",
                ),
            )
            quarantine_path = root / "quarantine" / "import-id"
            quarantine_path.mkdir(parents=True)
            (quarantine_path / "track.mp3").write_bytes(b"partial")
            record = ImportRecord(
                id=uuid4(),
                source="personal_1337x",
                torrent_id="1",
                info_hash="ABC",
                magnet_link="magnet:?xt=urn:btih:ABC",
                uploader="mekamb",
                source_url="https://1337x.to/torrent/1/example/",
                status="downloading",
                quarantine_path=str(quarantine_path),
                error_message=None,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            await repository.add(record)

            canceled = await service.cancel_import(record.id)

            self.assertEqual(canceled.status, "canceled")
            self.assertEqual(downloader.deletes, [(f"mekamb-music:{record.id}", True)])
            self.assertFalse(quarantine_path.exists())

    async def test_cancel_import_refuses_cleanup_outside_quarantine(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repository = FakeRepository()
            downloader = FakeDownloader()
            service = ImportService(
                repository=repository,
                downloader=downloader,
                planner=QuarantinePlanner(
                    quarantine_root=root / "quarantine",
                    torrent_download_root=Path("/downloads/incomplete"),
                    library_root=root / "library",
                ),
            )
            unsafe_path = root / "outside"
            unsafe_path.mkdir()
            record = ImportRecord(
                id=uuid4(),
                source="personal_1337x",
                torrent_id="1",
                info_hash="ABC",
                magnet_link="magnet:?xt=urn:btih:ABC",
                uploader="mekamb",
                source_url="https://1337x.to/torrent/1/example/",
                status="downloading",
                quarantine_path=str(unsafe_path),
                error_message=None,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            await repository.add(record)

            with self.assertRaises(SandboxViolation):
                await service.cancel_import(record.id)

            self.assertTrue(unsafe_path.exists())

    def test_planner_rejects_library_as_quarantine(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            planner = QuarantinePlanner(
                quarantine_root=root / "library",
                torrent_download_root=Path("/downloads/incomplete"),
                library_root=root / "library",
            )

            with self.assertRaises(SandboxViolation):
                planner.plan(__import__("uuid").uuid4())


if __name__ == "__main__":
    unittest.main()
