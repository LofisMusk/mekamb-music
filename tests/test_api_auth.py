"""HTTP-level tests for the auth/admin routers: exercises the real FastAPI
wiring (dependency graph, error mapping, response schemas) against a shared
in-memory SQLite DB and a fake Redis.
"""
from __future__ import annotations

import asyncio
import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import db_session, redis_client
from app.core import config as config_module
from app.db.models import Base
from app.main import app


class _FakeRedis:
    def __init__(self) -> None:
        self.counters: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def expire(self, key: str, seconds: int) -> None:
        return None

    async def delete(self, key: str) -> None:
        self.counters.pop(key, None)


@pytest.fixture
def client(monkeypatch):
    # A temp-file SQLite DB is shared across connections/event loops, which keeps
    # the sync TestClient (its own loop) and the setup step consistent.
    fd, db_path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    maker = async_sessionmaker(engine, expire_on_commit=False)

    asyncio.run(_create_all(engine))

    async def _db_override():
        async with maker() as session:
            yield session

    fake_redis = _FakeRedis()

    # An admin bootstrap email so we can get an approved admin without a prior admin.
    monkeypatch.setattr(config_module.settings, "admin_emails", "admin@b.com")

    app.dependency_overrides[db_session] = _db_override
    app.dependency_overrides[redis_client] = lambda: fake_redis
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(db_session, None)
        app.dependency_overrides.pop(redis_client, None)
        asyncio.run(engine.dispose())
        os.unlink(db_path)


async def _create_all(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def test_register_pending_then_login_blocked_until_approved(client):
    # Fresh signup -> pending, no token issued.
    resp = client.post(
        "/auth/register",
        json={"email": "a@b.com", "username": "alice", "password": "supersecret"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["token"] is None
    assert body["user"]["status"] == "pending"

    # Login blocked while pending.
    login = client.post("/auth/login", json={"identifier": "alice", "password": "supersecret"})
    assert login.status_code == 403
    assert login.json()["detail"]["code"] == "account_pending"


def test_admin_bootstrap_can_approve_and_user_logs_in(client):
    # Bootstrap admin (email allowlisted) is approved immediately and gets a token.
    admin_reg = client.post(
        "/auth/register",
        json={"email": "admin@b.com", "username": "admin", "password": "supersecret"},
    )
    assert admin_reg.status_code == 201
    admin_token = admin_reg.json()["token"]
    assert admin_token
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Pending user.
    client.post(
        "/auth/register",
        json={"email": "a@b.com", "username": "alice", "password": "supersecret"},
    )

    # Admin lists pending users and approves alice.
    pending = client.get("/admin/users", params={"status": "pending"}, headers=admin_headers)
    assert pending.status_code == 200
    users = pending.json()["users"]
    assert len(users) == 1 and users[0]["username"] == "alice"
    alice_id = users[0]["id"]

    approve = client.post(f"/admin/users/{alice_id}/approve", headers=admin_headers)
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"

    # Alice can now log in and hit /auth/me.
    login = client.post("/auth/login", json={"identifier": "a@b.com", "password": "supersecret"})
    assert login.status_code == 200
    token = login.json()["token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["username"] == "alice"


def test_non_admin_cannot_reach_admin_panel(client):
    admin_reg = client.post(
        "/auth/register",
        json={"email": "admin@b.com", "username": "admin", "password": "supersecret"},
    )
    admin_headers = {"Authorization": f"Bearer {admin_reg.json()['token']}"}
    client.post(
        "/auth/register",
        json={"email": "a@b.com", "username": "alice", "password": "supersecret"},
    )
    users = client.get("/admin/users", headers=admin_headers).json()["users"]
    alice_id = next(u["id"] for u in users if u["username"] == "alice")
    client.post(f"/admin/users/{alice_id}/approve", headers=admin_headers)

    login = client.post("/auth/login", json={"identifier": "alice", "password": "supersecret"})
    alice_headers = {"Authorization": f"Bearer {login.json()['token']}"}

    forbidden = client.get("/admin/users", headers=alice_headers)
    assert forbidden.status_code == 403


def test_raw_bearer_token_never_authenticates(client):
    # There is no configured raw-token scheme anymore: an arbitrary bearer value
    # (even one that looks like a token) must be rejected on protected endpoints.
    resp = client.get("/playback/state", headers={"Authorization": "Bearer legacy-token-1"})
    assert resp.status_code == 401


def test_missing_token_still_401(client):
    assert client.get("/playback/state").status_code == 401
