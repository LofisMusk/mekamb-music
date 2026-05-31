from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Mekamb Music"
    environment: str = "local"
    api_token: str = Field(default="")

    personal_1337x_uploader: str | None = None
    personal_1337x_base_url: str = "https://1337x.to"
    personal_1337x_max_pages: int = 1

    database_url: str = "postgresql+asyncpg://music:music@localhost:5432/music"
    redis_url: str = "redis://localhost:6379/0"
    import_queue_name: str = "mekamb-music:import-events"

    s3_endpoint_url: str | None = "http://localhost:9000"
    s3_access_key_id: str = "minio"
    s3_secret_access_key: str = "miniosecret"
    s3_bucket: str = "music-library"
    s3_region: str = "us-east-1"
    storage_backend: str = "local"

    quarantine_root: Path = Path("data/quarantine")
    library_root: Path = Path("data/library")
    torrent_download_root: Path = Path("/downloads/incomplete")
    torrent_rpc_url: str = "http://localhost:8080"
    torrent_rpc_username: str = "admin"
    torrent_rpc_password: str = "adminadmin"
    import_worker_interval_seconds: int = 15
    cleanup_quarantine_after_import: bool = True
    remove_torrent_after_import: bool = True

    # ── Cache TTL ────────────────────────────────────────────────────────────
    cache_ttl_days: int = 30
    cache_cleanup_interval_seconds: int = 3600

    # ── Redis search cache ───────────────────────────────────────────────────
    search_cache_ttl_seconds: int = 300

    @property
    def personal_1337x_enabled(self) -> bool:
        return bool(self.personal_1337x_uploader and self.personal_1337x_uploader.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
