"""Account authentication service.

All account logic lives here (register, claim-token migration, login, sessions,
password change, admin approval) so the route handlers stay thin and the security
rules are testable in one place. Functions take an ``AsyncSession`` and mutate it;
callers are responsible for the surrounding transaction (``commit``).

Security model (hardened so approval cannot be bypassed):
  * Fresh signups are created ``pending``. There is NO code path that mints a
    session for a non-``approved`` user — ``register`` never returns a token and
    ``login``/``resolve_session_token`` refuse anything that isn't ``approved``.
  * ``is_admin`` is never settable from a request body; it is only granted by the
    ``ADMIN_EMAILS`` bootstrap allowlist or by an existing admin.
  * Claiming a valid legacy token yields an ``approved`` account (the token proves
    prior authorization) bound to that token's ``api_key_id`` — but only once per
    ``api_key_id``, so a token can't be used to hijack an already-migrated scope.
  * Session tokens are 256-bit random and stored only as SHA-256 hashes.
"""
from __future__ import annotations

import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ApiKeyIdentity, match_bearer_token
from app.core.config import Settings, settings
from app.core.passwords import hash_password, needs_rehash, verify_password
from app.db.models import User, UserSession, utcnow

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_DISABLED = "disabled"
VALID_STATUSES = frozenset({STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED, STATUS_DISABLED})

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")


class AuthError(Exception):
    """An auth failure carrying a stable machine ``code`` and a safe message."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ── normalization / token helpers ────────────────────────────────────────────


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_username(username: str) -> str:
    return username.strip().lower()


def _as_aware(value: datetime) -> datetime:
    """Coerce a datetime to timezone-aware UTC. Postgres (DateTime(timezone=True))
    already returns aware values; this guards against drivers/paths that yield
    naive datetimes so comparisons never raise."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _generate_token() -> str:
    return secrets.token_urlsafe(32)


def _new_api_key_id() -> str:
    # Fits the 64-char api_key_id column and the normalize_api_key_id charset.
    return f"user_{uuid4().hex[:24]}"


def admin_email_set(cfg: Settings) -> set[str]:
    return {normalize_email(entry) for entry in cfg.admin_emails.split(",") if entry.strip()}


def _validate_new_credentials(*, email: str, username: str, password: str, cfg: Settings) -> None:
    if not _EMAIL_RE.match(email.strip()):
        raise AuthError("invalid_email", "Enter a valid email address.")
    if not _USERNAME_RE.match(username.strip()):
        raise AuthError(
            "invalid_username",
            "Username must be 3-64 characters: letters, numbers, and . _ - only.",
        )
    if len(password) < cfg.password_min_length:
        raise AuthError(
            "weak_password",
            f"Password must be at least {cfg.password_min_length} characters.",
        )


# ── lookups ──────────────────────────────────────────────────────────────────


async def get_user_by_identifier(session: AsyncSession, identifier: str) -> User | None:
    """Resolve a login identifier that may be either an email or a username."""
    key = identifier.strip().lower()
    if not key:
        return None
    return await session.scalar(
        select(User).where(
            or_(User.email_normalized == key, User.username_normalized == key)
        )
    )


async def _user_with_api_key_id(session: AsyncSession, api_key_id: str) -> User | None:
    return await session.scalar(select(User).where(User.api_key_id == api_key_id))


async def _assert_unique(session: AsyncSession, *, email_norm: str, username_norm: str) -> None:
    existing = await session.scalar(
        select(User).where(
            or_(User.email_normalized == email_norm, User.username_normalized == username_norm)
        )
    )
    if existing is not None:
        if existing.email_normalized == email_norm:
            raise AuthError("email_taken", "An account with this email already exists.")
        raise AuthError("username_taken", "This username is already taken.")


# ── registration & migration ─────────────────────────────────────────────────


async def register_user(
    session: AsyncSession,
    *,
    email: str,
    username: str,
    password: str,
    cfg: Settings = settings,
) -> User:
    """Open self-signup. Account is created ``pending`` (no access until an admin
    approves) unless the email is in the ``ADMIN_EMAILS`` bootstrap allowlist, in
    which case it is created as an approved admin so the first admin can get in."""
    if not cfg.registration_enabled:
        raise AuthError("registration_disabled", "Registration is currently disabled.")
    _validate_new_credentials(email=email, username=username, password=password, cfg=cfg)

    email_norm = normalize_email(email)
    username_norm = normalize_username(username)
    await _assert_unique(session, email_norm=email_norm, username_norm=username_norm)

    is_bootstrap_admin = email_norm in admin_email_set(cfg)
    user = User(
        email=email.strip(),
        email_normalized=email_norm,
        username=username.strip(),
        username_normalized=username_norm,
        password_hash=hash_password(password),
        api_key_id=_new_api_key_id(),
        status=STATUS_APPROVED if is_bootstrap_admin else STATUS_PENDING,
        is_admin=is_bootstrap_admin,
        approved_at=utcnow() if is_bootstrap_admin else None,
    )
    session.add(user)
    await session.flush()
    return user


async def claim_token(
    session: AsyncSession,
    *,
    email: str,
    username: str,
    password: str,
    token: str,
    cfg: Settings = settings,
) -> User:
    """Migrate a legacy bearer-token user to an email/username/password account.

    The supplied token must match a configured ``API_TOKEN(S)``. The new account
    inherits that token's ``api_key_id`` so the user's library, likes, plays and
    playback carry over, and is created ``approved`` (the token proves prior
    authorization). A given token/``api_key_id`` can only be claimed once, and
    from the moment it is claimed the raw token no longer authenticates —
    ``require_token`` rejects it with ``token_migrated`` — so the account's
    email/username/password fully replaces the token."""
    _validate_new_credentials(email=email, username=username, password=password, cfg=cfg)

    identity = match_bearer_token(cfg, f"Bearer {token.strip()}")
    if identity is None:
        raise AuthError("invalid_token", "That token is not valid.")

    if await _user_with_api_key_id(session, identity.id) is not None:
        raise AuthError(
            "token_already_claimed",
            "This token has already been migrated to an account.",
        )

    email_norm = normalize_email(email)
    username_norm = normalize_username(username)
    await _assert_unique(session, email_norm=email_norm, username_norm=username_norm)

    is_admin = email_norm in admin_email_set(cfg)
    user = User(
        email=email.strip(),
        email_normalized=email_norm,
        username=username.strip(),
        username_normalized=username_norm,
        password_hash=hash_password(password),
        api_key_id=identity.id,  # inherit the token's data scope — this is the migration
        status=STATUS_APPROVED,
        is_admin=is_admin,
        approved_at=utcnow(),
    )
    session.add(user)
    await session.flush()
    return user


# ── login / sessions ─────────────────────────────────────────────────────────


async def authenticate(session: AsyncSession, *, identifier: str, password: str) -> User:
    """Verify credentials and account status. Raises ``AuthError`` on failure.

    Wrong identifier and wrong password both yield the same generic
    ``invalid_credentials`` error so account existence isn't leaked. A correct
    login for a not-yet-approved account returns a status-specific error to its
    own owner (who already knows the account exists)."""
    user = await get_user_by_identifier(session, identifier)
    if user is None or not verify_password(password, user.password_hash):
        raise AuthError("invalid_credentials", "Incorrect email/username or password.")

    if user.status != STATUS_APPROVED:
        raise AuthError(_status_error_code(user.status), _status_error_message(user.status))

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        user.updated_at = utcnow()
    return user


def _status_error_code(status: str) -> str:
    return {
        STATUS_PENDING: "account_pending",
        STATUS_REJECTED: "account_rejected",
        STATUS_DISABLED: "account_disabled",
    }.get(status, "account_unavailable")


def _status_error_message(status: str) -> str:
    return {
        STATUS_PENDING: "Your account is awaiting admin approval.",
        STATUS_REJECTED: "Your account request was declined.",
        STATUS_DISABLED: "Your account has been disabled.",
    }.get(status, "Your account is not active.")


async def create_session(
    session: AsyncSession,
    user: User,
    *,
    cfg: Settings = settings,
    device_name: str | None = None,
) -> tuple[str, UserSession]:
    """Issue a new session. Returns the raw token (shown once) and the row that
    stores only its hash."""
    raw_token = _generate_token()
    record = UserSession(
        user_id=user.id,
        token_hash=_hash_token(raw_token),
        device_name=(device_name or None),
        expires_at=utcnow() + timedelta(days=cfg.auth_session_ttl_days),
    )
    session.add(record)
    await session.flush()
    return raw_token, record


async def resolve_session_token(session: AsyncSession, token: str) -> User | None:
    """Return the approved user for a session token, or ``None`` if the token is
    unknown/expired or the account is no longer approved (instant revocation on
    reject/disable). Refreshes ``last_used_at`` on success."""
    token = token.strip()
    if not token:
        return None
    record = await session.scalar(
        select(UserSession).where(UserSession.token_hash == _hash_token(token))
    )
    if record is None or _as_aware(record.expires_at) <= utcnow():
        return None
    user = await session.get(User, record.user_id)
    if user is None or user.status != STATUS_APPROVED:
        return None
    record.last_used_at = utcnow()
    return user


async def revoke_session(session: AsyncSession, token: str) -> None:
    record = await session.scalar(
        select(UserSession).where(UserSession.token_hash == _hash_token(token.strip()))
    )
    if record is not None:
        await session.delete(record)


async def revoke_all_sessions(session: AsyncSession, user_id: UUID) -> None:
    records = await session.scalars(
        select(UserSession).where(UserSession.user_id == user_id)
    )
    for record in records:
        await session.delete(record)


async def change_password(
    session: AsyncSession,
    user: User,
    *,
    current_password: str,
    new_password: str,
    cfg: Settings = settings,
) -> None:
    if not verify_password(current_password, user.password_hash):
        raise AuthError("invalid_credentials", "Current password is incorrect.")
    if len(new_password) < cfg.password_min_length:
        raise AuthError(
            "weak_password",
            f"Password must be at least {cfg.password_min_length} characters.",
        )
    user.password_hash = hash_password(new_password)
    user.updated_at = utcnow()


# ── admin approval ────────────────────────────────────────────────────────────


async def list_users(session: AsyncSession, *, status: str | None = None) -> list[User]:
    stmt = select(User).order_by(User.created_at.desc())
    if status is not None:
        stmt = stmt.where(User.status == status)
    return list(await session.scalars(stmt))


async def set_user_status(
    session: AsyncSession,
    *,
    target_user_id: UUID,
    status: str,
    admin: User,
) -> User:
    if status not in VALID_STATUSES:
        raise AuthError("invalid_status", "Unknown account status.")
    target = await session.get(User, target_user_id)
    if target is None:
        raise AuthError("user_not_found", "Account not found.")
    if target.id == admin.id and status != STATUS_APPROVED:
        # Guard against an admin locking themselves out mid-action.
        raise AuthError("cannot_change_self", "You cannot change your own account status.")

    target.status = status
    target.updated_at = utcnow()
    if status == STATUS_APPROVED:
        target.approved_at = utcnow()
        target.approved_by = admin.id
    else:
        # Kill any live sessions so a reject/disable takes effect immediately.
        await revoke_all_sessions(session, target.id)
    return target


def identity_for(user: User) -> ApiKeyIdentity:
    """The data-scope identity used by every downstream route (unchanged shape
    from the legacy token system)."""
    return ApiKeyIdentity(id=user.api_key_id, token="")
