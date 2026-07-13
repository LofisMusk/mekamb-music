import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from app.imports.domain import ImportRecord
from app.imports.service import ImportService, QuarantinePlanner, SandboxViolation


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


def _service(root: Path, repository: FakeRepository) -> ImportService:
    return ImportService(
        repository=repository,
        planner=QuarantinePlanner(
            quarantine_root=root / "quarantine",
            library_root=root / "library",
        ),
    )


def _album(root: Path) -> Path:
    source = root / "lidarr" / "Artist" / "Album"
    source.mkdir(parents=True)
    (source / "01 - track.flac").write_bytes(b"audio")
    return source


class ImportServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_lidarr_import_materializes_into_quarantine(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repository = FakeRepository()
            service = _service(root, repository)

            record = await service.create_lidarr_import(
                source_dir=_album(root),
                foreign_key="lidarr:42",
                name="Artist - Album",
            )

            self.assertEqual(record.source, "lidarr")
            self.assertIn("quarantine", record.quarantine_path)
            self.assertNotIn("/library", record.quarantine_path)
            self.assertEqual(record.status, "ready_to_import")
            copied = list(Path(record.quarantine_path).rglob("*.flac"))
            self.assertEqual(len(copied), 1)

    async def test_import_from_files_copies_only_named_files(self):
        # Lidarr uses a flat per-artist folder, so ingest must pick specific files.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            flat = root / "lidarr" / "Artist"
            flat.mkdir(parents=True)
            wanted = flat / "01 - Europa.mp3"
            wanted.write_bytes(b"audio")
            (flat / "01 - OtherAlbum.mp3").write_bytes(b"nope")  # different album, same folder
            repository = FakeRepository()
            service = _service(root, repository)

            record = await service.create_lidarr_import_from_files(
                files=[wanted, flat / "does-not-exist.mp3"],
                foreign_key="lidarr:mb-europa",
                name="Artist - Europa",
            )

            self.assertIsNotNone(record)
            copied = sorted(p.name for p in Path(record.quarantine_path).rglob("*.mp3"))
            self.assertEqual(copied, ["01 - Europa.mp3"])  # only the named file, not the neighbor

    async def test_import_from_files_returns_none_when_no_files_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = await _service(root, FakeRepository()).create_lidarr_import_from_files(
                files=[root / "gone.mp3"], foreign_key="lidarr:x", name="x"
            )
            self.assertIsNone(record)

    async def test_import_from_files_idempotent_by_foreign_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f = root / "t.mp3"
            f.write_bytes(b"a")
            repository = FakeRepository()
            service = _service(root, repository)
            a = await service.create_lidarr_import_from_files(files=[f], foreign_key="lidarr:9", name="a")
            b = await service.create_lidarr_import_from_files(files=[f], foreign_key="lidarr:9", name="a")
            self.assertEqual(a.id, b.id)
            self.assertEqual(len(repository.records), 1)

    async def test_lidarr_import_is_idempotent_by_foreign_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repository = FakeRepository()
            service = _service(root, repository)

            album = _album(root)
            first = await service.create_lidarr_import(
                source_dir=album, foreign_key="lidarr:42", name="a"
            )
            second = await service.create_lidarr_import(
                source_dir=album, foreign_key="lidarr:42", name="a"
            )

            self.assertEqual(first.id, second.id)
            self.assertEqual(len(repository.records), 1)

    async def test_cancel_import_removes_quarantine_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repository = FakeRepository()
            service = _service(root, repository)
            quarantine_path = root / "quarantine" / "import-id"
            quarantine_path.mkdir(parents=True)
            (quarantine_path / "track.mp3").write_bytes(b"partial")
            record = ImportRecord(
                id=uuid4(),
                source="lidarr",
                torrent_id="lidarr:1",
                info_hash="lidarr:1",
                magnet_link="",
                uploader="lidarr",
                source_url="lidarr",
                status="ready_to_import",
                quarantine_path=str(quarantine_path),
                error_message=None,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            await repository.add(record)

            canceled = await service.cancel_import(record.id)

            self.assertEqual(canceled.status, "canceled")
            self.assertFalse(quarantine_path.exists())

    async def test_cancel_import_refuses_cleanup_outside_quarantine(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repository = FakeRepository()
            service = _service(root, repository)
            unsafe_path = root / "outside"
            unsafe_path.mkdir()
            record = ImportRecord(
                id=uuid4(),
                source="lidarr",
                torrent_id="lidarr:1",
                info_hash="lidarr:1",
                magnet_link="",
                uploader="lidarr",
                source_url="lidarr",
                status="ready_to_import",
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
                library_root=root / "library",
            )

            with self.assertRaises(SandboxViolation):
                planner.plan(uuid4())


if __name__ == "__main__":
    unittest.main()
