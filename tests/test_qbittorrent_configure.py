from pathlib import Path

import pytest

from scripts.qbittorrent_configure import configure_qbittorrent, qbittorrent_password_hash


def test_qbittorrent_password_hash_matches_qbittorrent_pbkdf2_format():
    password_hash = qbittorrent_password_hash("adminadmin", salt=b"\0" * 16)

    assert password_hash.startswith("@ByteArray(AAAAAAAAAAAAAAAAAAAAAA==:")
    assert password_hash.endswith(")")


def test_configure_qbittorrent_writes_webui_credentials(tmp_path: Path):
    config_path = tmp_path / "qBittorrent.conf"
    config_path.write_text(
        "\n".join(
            [
                "[AutoRun]",
                "enabled=false",
                "[Preferences]",
                "WebUI\\Username=old",
                "WebUI\\Password_PBKDF2=\"old-hash\"",
                "WebUI\\Password_ha1=old-ha1",
                "WebUI\\Port=9090",
                "[BitTorrent]",
                "Session\\Port=6881",
                "",
            ]
        )
    )

    configure_qbittorrent(
        config_path=config_path,
        username="admin",
        password="adminadmin",
        webui_port="8080",
        password_hash="@ByteArray(test-salt:test-hash)",
    )

    payload = config_path.read_text()
    assert "[Preferences]" in payload
    assert "WebUI\\Username=admin\n" in payload
    assert 'WebUI\\Password_PBKDF2="@ByteArray(test-salt:test-hash)"\n' in payload
    assert "WebUI\\Port=8080\n" in payload
    assert "WebUI\\Password_ha1" not in payload
    assert "[BitTorrent]\nSession\\Port=6881" in payload


def test_configure_qbittorrent_creates_preferences_section(tmp_path: Path):
    config_path = tmp_path / "qBittorrent.conf"

    configure_qbittorrent(
        config_path=config_path,
        username="admin",
        password="adminadmin",
        password_hash="@ByteArray(test-salt:test-hash)",
    )

    assert config_path.read_text() == (
        "[Preferences]\n"
        "WebUI\\Username=admin\n"
        'WebUI\\Password_PBKDF2="@ByteArray(test-salt:test-hash)"\n'
        "WebUI\\Port=8080\n"
    )


def test_configure_qbittorrent_requires_password(tmp_path: Path):
    with pytest.raises(RuntimeError, match="TORRENT_RPC_PASSWORD"):
        configure_qbittorrent(config_path=tmp_path / "qBittorrent.conf", username="admin", password="")
