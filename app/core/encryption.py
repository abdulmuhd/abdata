"""Symmetric encryption for sensitive data at rest (API credentials, etc.).

Uses Fernet (AES-128-CBC) with a key derived from the application's SECRET_KEY.
The key is derived via PBKDF2-HMAC-SHA256 with a fixed salt so it's deterministic
per SECRET_KEY — same SECRET_KEY always decrypts the same data.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_PREFIX = "enc1:"  # marks a value as encrypted


def _derive_key(secret: str) -> bytes:
    """Derive a 32-byte Fernet key from the app secret."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"zaply-cred-salt-v1",
        iterations=100_000,
    )
    raw = kdf.derive(secret.encode())
    return base64.urlsafe_b64encode(raw)


def encrypt(plaintext: str, secret: str) -> str:
    """Encrypt a string value. Returns a prefixed string that can be detected."""
    if plaintext.startswith(_PREFIX):
        return plaintext  # already encrypted
    f = Fernet(_derive_key(secret))
    token = f.encrypt(plaintext.encode())
    return _PREFIX + token.decode()


def decrypt(ciphertext: str, secret: str) -> str:
    """Decrypt a prefixed encrypted string. Returns plaintext as-is if not encrypted."""
    if not ciphertext.startswith(_PREFIX):
        return ciphertext  # legacy plain-text value
    f = Fernet(_derive_key(secret))
    try:
        return f.decrypt(ciphertext[len(_PREFIX):].encode()).decode()
    except InvalidToken:
        return ciphertext  # can't decrypt — return as-is
