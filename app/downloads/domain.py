from __future__ import annotations

from dataclasses import asdict, dataclass
from uuid import UUID

from app.imports.domain import ImportRecord


@dataclass(frozen=True)
class TorrentRuntimeStatus:
    name: str
    info_hash: str
    state: str
    progress: float
    size_bytes: int
    downloaded_bytes: int
    download_speed_bytes: int
    eta_seconds: int
    save_path: str

    @property
    def is_complete(self) -> bool:
        complete_states = {"uploading", "stalledUP", "forcedUP", "queuedUP", "checkingUP", "pausedUP"}
        return self.progress >= 1.0 or self.state in complete_states

    @classmethod
    def from_qbittorrent(cls, payload: dict[str, object]) -> "TorrentRuntimeStatus":
        return cls(
            name=str(payload.get("name") or ""),
            info_hash=str(payload.get("hash") or ""),
            state=str(payload.get("state") or ""),
            progress=float(payload.get("progress") or 0.0),
            size_bytes=int(payload.get("size") or 0),
            downloaded_bytes=int(payload.get("downloaded") or 0),
            download_speed_bytes=int(payload.get("dlspeed") or 0),
            eta_seconds=int(payload.get("eta") or 0),
            save_path=str(payload.get("save_path") or ""),
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class DownloadStatus:
    import_record: ImportRecord
    torrent: TorrentRuntimeStatus | None

    def to_dict(self) -> dict[str, object]:
        return {
            "import": self.import_record.to_dict(),
            "torrent": self.torrent.to_dict() if self.torrent else None,
        }
