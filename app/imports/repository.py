from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ImportJob
from app.imports.domain import ImportNotFound, ImportRecord


class SqlAlchemyImportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, record: ImportRecord) -> ImportRecord:
        model = ImportJob(
            id=record.id,
            source=record.source,
            torrent_id=record.torrent_id,
            info_hash=record.info_hash,
            magnet_link=record.magnet_link,
            uploader=record.uploader,
            source_url=record.source_url,
            status=record.status,
            quarantine_path=record.quarantine_path,
            error_message=record.error_message,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
        self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)
        return import_record_from_model(model)

    async def get(self, import_id: UUID) -> ImportRecord:
        record = await self.session.get(ImportJob, import_id)
        if record is None:
            raise ImportNotFound(f"Import {import_id} not found.")
        return import_record_from_model(record)

    async def get_by_info_hash(self, info_hash: str) -> ImportRecord | None:
        record = await self.session.scalar(
            select(ImportJob)
            .where(ImportJob.info_hash == info_hash)
            .order_by(ImportJob.created_at.desc())
            .limit(1)
        )
        return import_record_from_model(record) if record else None

    async def list(self, *, status: str | None, limit: int, offset: int) -> list[ImportRecord]:
        statement = select(ImportJob).order_by(ImportJob.created_at.desc()).limit(limit).offset(offset)
        if status:
            statement = statement.where(ImportJob.status == status)
        records = await self.session.scalars(statement)
        return [import_record_from_model(record) for record in records]

    async def update(self, record: ImportRecord) -> ImportRecord:
        model = await self.session.get(ImportJob, record.id)
        if model is None:
            raise ImportNotFound(f"Import {record.id} not found.")
        model.status = record.status
        model.error_message = record.error_message
        model.updated_at = record.updated_at
        await self.session.commit()
        await self.session.refresh(model)
        return import_record_from_model(model)


def import_record_from_model(model: ImportJob) -> ImportRecord:
    return ImportRecord(
        id=model.id,
        source=model.source,
        torrent_id=model.torrent_id,
        info_hash=model.info_hash,
        magnet_link=model.magnet_link,
        uploader=model.uploader,
        source_url=model.source_url,
        status=model.status,
        quarantine_path=model.quarantine_path,
        error_message=model.error_message,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )
