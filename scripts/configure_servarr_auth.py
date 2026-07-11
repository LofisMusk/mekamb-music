#!/usr/bin/env python3
import base64
import hashlib
import os
import sqlite3
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path


ITERATIONS = 10000
SALT_BYTES = 16
HASH_BYTES = 32


def env_value(*names, default=None):
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


def ensure_xml_value(root, tag, value):
    node = root.find(tag)
    if node is None:
        node = ET.SubElement(root, tag)
    node.text = value


def configure_xml(config_path, auth_method, auth_required, api_key):
    if not config_path.exists():
        print(f"{config_path}: missing, skipping config.xml update")
        return

    tree = ET.parse(config_path)
    root = tree.getroot()

    ensure_xml_value(root, "AuthenticationMethod", auth_method)
    ensure_xml_value(root, "AuthenticationRequired", auth_required)
    if api_key:
        ensure_xml_value(root, "ApiKey", api_key)

    ET.indent(tree, space="  ")
    tree.write(config_path, encoding="utf-8", xml_declaration=False)


def hash_password(password):
    salt = os.urandom(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha512",
        password.encode("utf-8"),
        salt,
        ITERATIONS,
        HASH_BYTES,
    )
    return (
        base64.b64encode(digest).decode("ascii"),
        base64.b64encode(salt).decode("ascii"),
    )


def configure_user(db_path, username, password):
    if not db_path.exists():
        print(f"{db_path}: missing, skipping user update")
        return

    password_hash, salt = hash_password(password)
    normalized_username = username.lower()

    with sqlite3.connect(db_path) as db:
        exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'Users'"
        ).fetchone()
        if not exists:
            print(f"{db_path}: Users table missing, skipping user update")
            return

        current = db.execute("SELECT Id FROM Users ORDER BY Id LIMIT 1").fetchone()
        if current:
            db.execute(
                """
                UPDATE Users
                SET Username = ?, Password = ?, Salt = ?, Iterations = ?
                WHERE Id = ?
                """,
                (normalized_username, password_hash, salt, ITERATIONS, current[0]),
            )
            db.execute("DELETE FROM Users WHERE Id <> ?", (current[0],))
        else:
            db.execute(
                """
                INSERT INTO Users (Identifier, Username, Password, Salt, Iterations)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    normalized_username,
                    password_hash,
                    salt,
                    ITERATIONS,
                ),
            )
        db.commit()


def configure_app(name, prefix, db_name):
    config_dir = Path(env_value(f"{prefix}_CONFIG_DIR", default=f"/{name}-config"))
    username = env_value(
        f"{prefix}_WEBUI_USERNAME",
        "SERVARR_WEBUI_USERNAME",
        default="mekamb",
    )
    password = env_value(f"{prefix}_WEBUI_PASSWORD", "SERVARR_WEBUI_PASSWORD")
    auth_method = env_value(f"{prefix}_AUTH_METHOD", default="Forms")
    auth_required = env_value(f"{prefix}_AUTH_REQUIRED", default="Enabled")
    api_key = env_value(f"{prefix}_API_KEY")

    if not password:
        raise SystemExit(
            f"{prefix}_WEBUI_PASSWORD or SERVARR_WEBUI_PASSWORD must be set"
        )

    configure_xml(config_dir / "config.xml", auth_method, auth_required, api_key)
    configure_user(config_dir / db_name, username, password)
    print(f"{name}: configured WebUI user '{username}'")


def main():
    configure_app("lidarr", "LIDARR", "lidarr.db")
    configure_app("prowlarr", "PROWLARR", "prowlarr.db")


if __name__ == "__main__":
    main()
