#!/usr/bin/env python3
"""Install and configure the TrevTV/Lidarr.Plugin.Deezer plugin in Lidarr.

Runs as a one-shot compose job (``lidarr-deezer-init``) after Lidarr is up. It:

  1. waits for the Lidarr API,
  2. installs the Deezer plugin via the ``InstallPlugin`` command (if missing)
     and restarts Lidarr so the plugin loads,
  3. adds a Deezer indexer and a Deezer download client, discovering the exact
     field names from Lidarr's live schemas (so this keeps working even as the
     plugin's fields change) and injecting ``DEEZER_ARL`` / the download dir,
  4. enables the Deezer protocol on every delay profile (best effort).

Everything is idempotent: re-running skips anything already present. Only the
Python standard library is used so it runs on a bare ``python:*-alpine`` image.

Environment:
  LIDARR_URL              default http://lidarr:8686
  LIDARR_API_KEY          required
  DEEZER_ARL              optional (plugin auto-picks one when blank)
  DEEZER_PLUGIN_URL       default https://github.com/TrevTV/Lidarr.Plugin.Deezer
  DEEZER_DOWNLOAD_DIR     default /downloads/deezer
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

LIDARR_URL = os.environ.get("LIDARR_URL", "http://lidarr:8686").rstrip("/")
API_KEY = os.environ.get("LIDARR_API_KEY", "").strip()
ARL = os.environ.get("DEEZER_ARL", "").strip()
PLUGIN_URL = os.environ.get(
    "DEEZER_PLUGIN_URL", "https://github.com/TrevTV/Lidarr.Plugin.Deezer"
).strip()
DOWNLOAD_DIR = os.environ.get("DEEZER_DOWNLOAD_DIR", "/downloads/deezer").strip()


def log(msg: str) -> None:
    print(f"[deezer-init] {msg}", flush=True)


def api(method: str, path: str, body=None, timeout: int = 30):
    url = f"{LIDARR_URL}/api/v1{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"X-Api-Key": API_KEY, "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode()
        return resp.status, (json.loads(raw) if raw else None)


def wait_for_api(label: str, attempts: int = 120, delay: float = 5.0) -> None:
    for i in range(attempts):
        try:
            status, _ = api("GET", "/system/status", timeout=10)
            if status == 200:
                log(f"Lidarr API ready ({label}).")
                return
        except Exception as exc:  # noqa: BLE001 — any failure = not ready yet
            if i % 6 == 0:
                log(f"waiting for Lidarr API ({label}): {exc}")
        time.sleep(delay)
    raise SystemExit(f"Lidarr API never became ready ({label}).")


def deezer_plugin_installed() -> bool:
    _, plugins = api("GET", "/system/plugins")
    for p in plugins or []:
        url = (p.get("githubUrl") or "").rstrip("/").lower()
        if url == PLUGIN_URL.rstrip("/").lower() or "deezer" in (p.get("name") or "").lower():
            return True
    return False


def wait_for_command(command_id: int, attempts: int = 60, delay: float = 3.0) -> None:
    for _ in range(attempts):
        _, cmd = api("GET", f"/command/{command_id}")
        state = (cmd or {}).get("status", "")
        if state in ("completed", "failed", "aborted"):
            log(f"InstallPlugin command finished: {state}")
            if state != "completed":
                raise SystemExit(f"InstallPlugin command {state}.")
            return
        time.sleep(delay)
    raise SystemExit("InstallPlugin command did not finish in time.")


def install_plugin() -> None:
    if deezer_plugin_installed():
        log("Deezer plugin already installed.")
        return
    log(f"installing Deezer plugin from {PLUGIN_URL} ...")
    _, cmd = api("POST", "/command", {"name": "InstallPlugin", "githubUrl": PLUGIN_URL})
    wait_for_command(cmd["id"])
    log("restarting Lidarr to load the plugin ...")
    try:
        api("POST", "/system/restart")
    except urllib.error.URLError:
        pass  # the restart tears down the connection; expected
    time.sleep(10)
    wait_for_api("after plugin restart")


def find_deezer_schema(kind: str):
    _, schemas = api("GET", f"/{kind}/schema")
    for s in schemas or []:
        impl = (s.get("implementation") or "") + (s.get("implementationName") or "")
        if "deezer" in impl.lower():
            return s
    return None


def set_field(schema: dict, name_matches, value) -> bool:
    """Set the first field whose name matches; return True if one was set."""
    for f in schema.get("fields", []):
        if name_matches(f.get("name", "")):
            f["value"] = value
            return True
    return False


def already_has_deezer(kind: str) -> bool:
    _, items = api("GET", f"/{kind}")
    for it in items or []:
        if "deezer" in (it.get("implementation") or "").lower():
            return True
    return False


def add_indexer() -> None:
    if already_has_deezer("indexer"):
        log("Deezer indexer already present.")
        return
    schema = find_deezer_schema("indexer")
    if schema is None:
        raise SystemExit("Deezer indexer schema not found — plugin did not load.")
    schema["name"] = "Deezer"
    schema["enable"] = True
    if ARL:
        if set_field(schema, lambda n: "arl" in n.lower(), ARL):
            log("injected DEEZER_ARL into indexer.")
    api("POST", "/indexer", schema)
    log("added Deezer indexer.")


def add_download_client() -> None:
    if already_has_deezer("downloadclient"):
        log("Deezer download client already present.")
        return
    schema = find_deezer_schema("downloadclient")
    if schema is None:
        raise SystemExit("Deezer download client schema not found — plugin did not load.")
    schema["name"] = "Deezer"
    schema["enable"] = True
    if ARL:
        set_field(schema, lambda n: "arl" in n.lower(), ARL)
    # Point the plugin's output at a real volume path Lidarr can import from.
    set_field(
        schema,
        lambda n: any(k in n.lower() for k in ("path", "directory", "folder", "dir")),
        DOWNLOAD_DIR,
    )
    api("POST", "/downloadclient", schema)
    log(f"added Deezer download client (path {DOWNLOAD_DIR}).")


def enable_deezer_in_delay_profiles() -> None:
    """Best effort: turn the Deezer protocol on for each delay profile."""
    try:
        _, profiles = api("GET", "/delayprofile")
    except Exception as exc:  # noqa: BLE001
        log(f"could not read delay profiles ({exc}); enable Deezer manually in Settings → Profiles.")
        return
    changed = 0
    for prof in profiles or []:
        items = prof.get("items")
        if not isinstance(items, list):
            continue
        touched = False
        for entry in items:
            proto = json.dumps(entry).lower()
            if "deezer" in proto and entry.get("allowed") is not True:
                entry["allowed"] = True
                touched = True
        if touched:
            try:
                api("PUT", f"/delayprofile/{prof['id']}", prof)
                changed += 1
            except Exception as exc:  # noqa: BLE001
                log(f"could not update delay profile {prof.get('id')} ({exc}).")
    if changed:
        log(f"enabled Deezer on {changed} delay profile(s).")
    else:
        log("no delay-profile change needed (or enable Deezer manually in Settings → Profiles).")


def main() -> None:
    if not API_KEY:
        raise SystemExit("LIDARR_API_KEY is required.")
    wait_for_api("startup")
    install_plugin()
    add_indexer()
    add_download_client()
    enable_deezer_in_delay_profiles()
    log("Deezer integration configured.")


if __name__ == "__main__":
    try:
        main()
    except SystemExit as exc:
        if exc.code not in (0, None):
            log(f"FAILED: {exc}")
        raise
    except Exception as exc:  # noqa: BLE001
        log(f"FAILED: {exc}")
        sys.exit(1)
