from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path


DEFAULT_CONFIG_PATH = Path("/config/qBittorrent/qBittorrent.conf")
PBKDF2_ITERATIONS = 100_000
PBKDF2_ALGORITHM = "sha512"


def qbittorrent_password_hash(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM,
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    encoded_salt = base64.b64encode(salt).decode("ascii")
    encoded_digest = base64.b64encode(digest).decode("ascii")
    return f"@ByteArray({encoded_salt}:{encoded_digest})"


def configure_qbittorrent(
    *,
    config_path: Path,
    username: str,
    password: str,
    webui_port: str = "8080",
    password_hash: str | None = None,
) -> None:
    if not username.strip():
        raise RuntimeError("TORRENT_RPC_USERNAME is required.")
    if not password:
        raise RuntimeError("TORRENT_RPC_PASSWORD is required.")

    config_path.parent.mkdir(parents=True, exist_ok=True)
    lines = config_path.read_text().splitlines(keepends=True) if config_path.exists() else []
    updates = {
        "WebUI\\Username": username.strip(),
        "WebUI\\Password_PBKDF2": f'"{password_hash or qbittorrent_password_hash(password)}"',
        "WebUI\\Port": str(webui_port),
    }
    remove_keys = {
        "WebUI\\Password",
        "WebUI\\Password_ha1",
    }
    config_path.write_text(_merge_preferences(lines, updates=updates, remove_keys=remove_keys))


def _merge_preferences(
    lines: list[str],
    *,
    updates: dict[str, str],
    remove_keys: set[str],
) -> str:
    output: list[str] = []
    in_preferences = False
    found_preferences = False
    written: set[str] = set()

    def write_missing_preferences() -> None:
        for key, value in updates.items():
            if key not in written:
                output.append(f"{key}={value}\n")
                written.add(key)

    for line in lines:
        stripped = line.strip()
        is_section = stripped.startswith("[") and stripped.endswith("]")
        if is_section:
            if in_preferences:
                write_missing_preferences()
            in_preferences = stripped == "[Preferences]"
            found_preferences = found_preferences or in_preferences
            output.append(line)
            continue

        if in_preferences and "=" in line:
            key = line.split("=", 1)[0].strip()
            if key in updates:
                if key not in written:
                    output.append(f"{key}={updates[key]}\n")
                    written.add(key)
                continue
            if key in remove_keys:
                continue

        output.append(line)

    if found_preferences:
        if in_preferences:
            write_missing_preferences()
    else:
        if output and output[-1].strip():
            output.append("\n")
        output.append("[Preferences]\n")
        write_missing_preferences()

    return "".join(output)


def main() -> None:
    configure_qbittorrent(
        config_path=Path(os.environ.get("QBITTORRENT_CONFIG_PATH", DEFAULT_CONFIG_PATH)),
        username=os.environ.get("TORRENT_RPC_USERNAME", "admin"),
        password=os.environ.get("TORRENT_RPC_PASSWORD", ""),
        webui_port=os.environ.get("WEBUI_PORT", "8080"),
    )


if __name__ == "__main__":
    main()
