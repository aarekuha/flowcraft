from __future__ import annotations

import hashlib
import hmac
import secrets


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived_key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=64,
    )
    return f"scrypt${salt.hex()}${derived_key.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, salt_hex, expected_hex = password_hash.split("$", maxsplit=2)
    except ValueError:
        return False

    if algorithm != "scrypt":
        return False

    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(expected_hex)
    derived_key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=len(expected),
    )
    return hmac.compare_digest(derived_key, expected)


def generate_session_token() -> str:
    return secrets.token_urlsafe(48)
