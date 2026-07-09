from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Mekamb Music"
    environment: str = "local"
    api_token: str = Field(default="")
    api_tokens: str = Field(default="")
    instance_id: str = "local"

    personal_1337x_base_url: str = "https://1337x.to"
    personal_1337x_base_urls: str = ""
    personal_1337x_max_pages: int = 1
    piratebay_api_base_url: str = "https://apibay.org"
    piratebay_category: int = 100
    music_indexer_prowlarr_url: str = ""
    music_indexer_torznab_urls: str = ""
    music_indexer_api_key: str = ""
    music_indexer_categories: str = "3000"

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
    torrent_listen_port: int = 6881
    import_worker_interval_seconds: int = 15
    cleanup_quarantine_after_import: bool = True
    remove_torrent_after_import: bool = True

    # ── Cache TTL ────────────────────────────────────────────────────────────
    cache_ttl_days: int = 30
    cache_cleanup_interval_seconds: int = 3600
    playback_prefetch_count: int = 2

    # ── Transcoding (lossless → AAC for the "AAC" / "Auto" playback quality) ──
    transcode_enabled: bool = True
    transcode_cache_root: Path = Path("data/transcode")
    transcode_aac_bitrate: str = "256k"

    recommendation_sources: str = "indexer"
    recommendation_auto_import_limit: int = 3
    recommendation_min_seeders: int = 1
    recommendation_use_gemini: bool = True
    recommendation_gemini_candidate_limit: int = 24
    recommendation_scan_limit: int = 2000
    recommendation_cache_ttl_seconds: int = 90
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"
    gemini_timeout_seconds: float = 8.0
    gemini_rerank_cache_ttl_seconds: int = 3600

    # ── Automatic audio feature extraction ───────────────────────────────────
    audio_feature_worker_interval_seconds: int = 60
    audio_feature_batch_size: int = 25
    audio_feature_current_version: str = "v2"
    audio_feature_enable_hpss: bool = True

    # ── Cross-user collaborative filtering (item-item co-occurrence) ──────────
    collaborative_recompute_interval_seconds: int = 21_600
    collaborative_session_gap_minutes: int = 30
    collaborative_cooccurrence_window: int = 3
    collaborative_top_k: int = 30
    collaborative_like_cooccurrence_bonus: float = 0.5
    recommendation_collaborative_weight: float = 20.0
    collaborative_max_session_tracks: int = 200

    # ── Session-aware sequencing (arc ordering + explore/exploit discovery) ───
    recommendation_discovery_slot_ratio: float = 0.2
    recommendation_sequencing_enabled: bool = True

    # ── Redis search cache ───────────────────────────────────────────────────
    search_cache_ttl_seconds: int = 300

    # ── Accounts / authentication ─────────────────────────────────────────────
    # Email/username/password auth layered on top of the legacy bearer tokens.
    # New signups land in `pending` and cannot authenticate until an admin
    # approves them; claiming a legacy token auto-approves (the token proves
    # prior authorization) and inherits that token's api_key_id so the user's
    # library, liked songs, plays and playback all carry over unchanged.
    registration_enabled: bool = True
    admin_emails: str = ""  # comma-separated emails auto-approved as admins on register/claim
    auth_session_ttl_days: int = 90
    password_min_length: int = 8
    auth_login_rate_limit: int = 10  # failed attempts per identifier within the window
    auth_login_rate_window_seconds: int = 300

@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
