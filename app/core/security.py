import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from .config import settings

PBKDF2_ITERATIONS = 390_000


# ── Password / PIN hashing (salted PBKDF2-SHA256) ────────────────────────


def _digest(secret: str, salt: bytes, iterations: int) -> str:
    return hashlib.pbkdf2_hmac("sha256", secret.encode(), salt, iterations).hex()


def hash_secret(secret: str) -> str:
    iterations = PBKDF2_ITERATIONS
    salt = secrets.token_bytes(16)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${_digest(secret, salt, iterations)}"


def verify_secret(secret: str, hashed: str) -> bool:
    try:
        _, iterations, salt_hex, digest = hashed.split("$")
        return hmac.compare_digest(_digest(secret, bytes.fromhex(salt_hex), int(iterations)), digest)
    except (ValueError, AttributeError):
        return False


hash_password = hash_secret
verify_password = verify_secret
hash_pin = hash_secret
verify_pin = verify_secret


# ── JWT ──────────────────────────────────────────────────────────────────


def _create_token(subject: str, token_type: str, expires_delta: timedelta, extra: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "jti": secrets.token_hex(8),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(user_id: int) -> str:
    return _create_token(str(user_id), "access", timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))


def create_refresh_token(user_id: int) -> str:
    return _create_token(str(user_id), "refresh", timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))


def create_reset_token(user_id: int) -> str:
    return _create_token(str(user_id), "password_reset", timedelta(minutes=settings.RESET_TOKEN_EXPIRE_MINUTES))


def decode_token(token: str, expected_type: str | None = None) -> dict[str, Any]:
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    if expected_type and payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"Expected {expected_type} token")
    return payload


# ── References & helpers ─────────────────────────────────────────────────


def generate_reference(prefix: str) -> str:
    stamp = format(int(time.time() * 1000), "x")[-9:].upper()
    rand = secrets.token_hex(4).upper()
    return f"ZP-{prefix}-{stamp}{rand}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
