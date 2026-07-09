"""Password hashing for account authentication.

Uses Argon2id (via ``argon2-cffi``) with the library's sane defaults. The rest of
the codebase treats a password hash as an opaque string, so switching parameters
or algorithms later only touches this module — ``needs_rehash`` lets callers
transparently upgrade stored hashes on the next successful login.
"""
from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True
