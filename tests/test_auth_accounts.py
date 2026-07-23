"""Service-level tests for the email/username/password account system.

Runs against a real in-memory SQLite async engine so the actual SQL (uniqueness
constraints, session lookups, status filtering) is exercised, not a fake. The
focus is the security contract: an unapproved account can never obtain a working
session.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth import service as auth
from app.auth.service import AuthError
from app.core.config import Settings
from app.db.models import Base


def _cfg(**overrides) -> Settings:
    base = dict(
        admin_emails="",
        registration_enabled=True,
        password_min_length=8,
        auth_session_ttl_days=90,
    )
    base.update(overrides)
    return Settings(**base)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


# ── registration & approval gate ──────────────────────────────────────────────


async def test_register_creates_pending_user(session):
    user = await auth.register_user(
        session, email="a@b.com", username="alice", password="supersecret", cfg=_cfg()
    )
    assert user.status == auth.STATUS_PENDING
    assert user.is_admin is False
    assert user.api_key_id.startswith("user_")


async def test_pending_user_cannot_authenticate(session):
    await auth.register_user(
        session, email="a@b.com", username="alice", password="supersecret", cfg=_cfg()
    )
    with pytest.raises(AuthError) as exc:
        await auth.authenticate(session, identifier="alice", password="supersecret")
    assert exc.value.code == "account_pending"


async def test_admin_approval_then_login_works(session):
    admin = await auth.register_user(
        session, email="admin@b.com", username="admin", password="supersecret",
        cfg=_cfg(admin_emails="admin@b.com"),
    )
    assert admin.is_admin and admin.status == auth.STATUS_APPROVED

    user = await auth.register_user(
        session, email="a@b.com", username="alice", password="supersecret", cfg=_cfg()
    )
    await auth.set_user_status(
        session, target_user_id=user.id, status=auth.STATUS_APPROVED, admin=admin
    )
    authed = await auth.authenticate(session, identifier="a@b.com", password="supersecret")
    assert authed.id == user.id
    assert authed.status == auth.STATUS_APPROVED


async def test_login_by_email_or_username(session):
    admin = await auth.register_user(
        session, email="admin@b.com", username="admin", password="supersecret",
        cfg=_cfg(admin_emails="admin@b.com"),
    )
    u = await auth.register_user(
        session, email="a@b.com", username="alice", password="supersecret", cfg=_cfg()
    )
    await auth.set_user_status(session, target_user_id=u.id, status=auth.STATUS_APPROVED, admin=admin)

    by_email = await auth.authenticate(session, identifier="A@B.com", password="supersecret")
    by_username = await auth.authenticate(session, identifier="ALICE", password="supersecret")
    assert by_email.id == by_username.id == u.id


async def test_wrong_password_is_generic_error(session):
    await auth.register_user(
        session, email="a@b.com", username="alice", password="supersecret", cfg=_cfg()
    )
    with pytest.raises(AuthError) as exc:
        await auth.authenticate(session, identifier="alice", password="wrong-password")
    assert exc.value.code == "invalid_credentials"


async def test_unknown_identifier_same_generic_error(session):
    with pytest.raises(AuthError) as exc:
        await auth.authenticate(session, identifier="ghost", password="whatever12")
    assert exc.value.code == "invalid_credentials"


async def test_duplicate_email_and_username_rejected(session):
    await auth.register_user(
        session, email="a@b.com", username="alice", password="supersecret", cfg=_cfg()
    )
    with pytest.raises(AuthError) as e1:
        await auth.register_user(
            session, email="A@B.com", username="other", password="supersecret", cfg=_cfg()
        )
    assert e1.value.code == "email_taken"
    with pytest.raises(AuthError) as e2:
        await auth.register_user(
            session, email="c@d.com", username="ALICE", password="supersecret", cfg=_cfg()
        )
    assert e2.value.code == "username_taken"


async def test_weak_password_rejected(session):
    with pytest.raises(AuthError) as exc:
        await auth.register_user(
            session, email="a@b.com", username="alice", password="short", cfg=_cfg()
        )
    assert exc.value.code == "weak_password"


async def test_registration_disabled(session):
    with pytest.raises(AuthError) as exc:
        await auth.register_user(
            session, email="a@b.com", username="alice", password="supersecret",
            cfg=_cfg(registration_enabled=False),
        )
    assert exc.value.code == "registration_disabled"


# ── sessions: issue / resolve / revoke ────────────────────────────────────────


async def _approved_user(session, cfg=None):
    cfg = cfg or _cfg(admin_emails="admin@b.com")
    admin = await auth.register_user(
        session, email="admin@b.com", username="admin", password="supersecret", cfg=cfg
    )
    u = await auth.register_user(
        session, email="a@b.com", username="alice", password="supersecret", cfg=_cfg()
    )
    await auth.set_user_status(session, target_user_id=u.id, status=auth.STATUS_APPROVED, admin=admin)
    return u


async def test_session_resolves_to_user(session):
    u = await _approved_user(session)
    token, _ = await auth.create_session(session, u)
    resolved = await auth.resolve_session_token(session, token)
    assert resolved is not None and resolved.id == u.id


async def test_logout_revokes_session(session):
    u = await _approved_user(session)
    token, _ = await auth.create_session(session, u)
    await auth.revoke_session(session, token)
    assert await auth.resolve_session_token(session, token) is None


async def test_disabling_user_revokes_access_immediately(session):
    cfg = _cfg(admin_emails="admin@b.com")
    admin = await auth.register_user(
        session, email="admin@b.com", username="admin", password="supersecret", cfg=cfg
    )
    u = await auth.register_user(
        session, email="a@b.com", username="alice", password="supersecret", cfg=_cfg()
    )
    await auth.set_user_status(session, target_user_id=u.id, status=auth.STATUS_APPROVED, admin=admin)
    token, _ = await auth.create_session(session, u)
    assert await auth.resolve_session_token(session, token) is not None

    await auth.set_user_status(session, target_user_id=u.id, status=auth.STATUS_DISABLED, admin=admin)
    # Existing session no longer resolves once the account is disabled.
    assert await auth.resolve_session_token(session, token) is None


async def test_change_password_requires_current_and_rehashes(session):
    u = await _approved_user(session)
    with pytest.raises(AuthError) as exc:
        await auth.change_password(
            session, u, current_password="nope-nope", new_password="brandnewpass", cfg=_cfg()
        )
    assert exc.value.code == "invalid_credentials"

    await auth.change_password(
        session, u, current_password="supersecret", new_password="brandnewpass", cfg=_cfg()
    )
    assert await auth.authenticate(session, identifier="alice", password="brandnewpass")


# ── admin guard rails ─────────────────────────────────────────────────────────


async def test_admin_cannot_disable_self(session):
    cfg = _cfg(admin_emails="admin@b.com")
    admin = await auth.register_user(
        session, email="admin@b.com", username="admin", password="supersecret", cfg=cfg
    )
    with pytest.raises(AuthError) as exc:
        await auth.set_user_status(
            session, target_user_id=admin.id, status=auth.STATUS_DISABLED, admin=admin
        )
    assert exc.value.code == "cannot_change_self"


async def test_list_users_status_filter(session):
    cfg = _cfg(admin_emails="admin@b.com")
    await auth.register_user(
        session, email="admin@b.com", username="admin", password="supersecret", cfg=cfg
    )
    await auth.register_user(
        session, email="a@b.com", username="alice", password="supersecret", cfg=_cfg()
    )
    pending = await auth.list_users(session, status=auth.STATUS_PENDING)
    approved = await auth.list_users(session, status=auth.STATUS_APPROVED)
    assert [u.username for u in pending] == ["alice"]
    assert [u.username for u in approved] == ["admin"]
