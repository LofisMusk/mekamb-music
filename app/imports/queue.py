from __future__ import annotations

from uuid import UUID

from redis.asyncio import Redis


class RedisImportQueue:
    def __init__(self, *, redis_url: str, queue_name: str) -> None:
        self.queue_name = queue_name
        self.client = Redis.from_url(redis_url, decode_responses=True)

    @classmethod
    def from_settings(cls, settings: object) -> "RedisImportQueue":
        return cls(
            redis_url=getattr(settings, "redis_url"),
            queue_name=getattr(settings, "import_queue_name", "mekamb-music:import-events"),
        )

    async def notify_import_changed(self, import_id: UUID) -> None:
        await self.client.lpush(self.queue_name, str(import_id))

    async def wait_for_import_changed(self, *, timeout_seconds: int) -> UUID | None:
        payload = await self.client.brpop(self.queue_name, timeout=timeout_seconds)
        if payload is None:
            return None

        _, raw_import_id = payload
        try:
            return UUID(raw_import_id)
        except ValueError:
            return None

    async def ping(self) -> None:
        await self.client.ping()

    async def close(self) -> None:
        await self.client.aclose()


async def check_redis(settings: object) -> None:
    queue = RedisImportQueue.from_settings(settings)
    try:
        await queue.ping()
    finally:
        await queue.close()
