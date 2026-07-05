from __future__ import annotations

from datetime import UTC, datetime, timedelta
import base64
import hashlib
import hmac
import json
import secrets
from typing import Any

from .config import Settings

_PBKDF2_ALGO = "pbkdf2_sha256"
_PBKDF2_ITERATIONS = 100_000


def _derive(password: str, salt: bytes, iterations: int, settings: Settings) -> bytes:
    # The server secret acts as a pepper on top of the per-user salt.
    material = f"{settings.secret_key}:{password}".encode()
    return hashlib.pbkdf2_hmac("sha256", material, salt, iterations)


def hash_password(password: str, settings: Settings) -> str:
    salt = secrets.token_bytes(16)
    derived = _derive(password, salt, _PBKDF2_ITERATIONS, settings)
    return "${}${}${}${}".format(
        _PBKDF2_ALGO,
        _PBKDF2_ITERATIONS,
        base64.b64encode(salt).decode(),
        base64.b64encode(derived).decode(),
    )


def verify_password(password: str, password_hash: str, settings: Settings) -> bool:
    try:
        _, algo, iterations, salt_b64, hash_b64 = password_hash.split("$")
        if algo != _PBKDF2_ALGO:
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        candidate = _derive(password, salt, int(iterations), settings)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, expected)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_access_token(payload: dict[str, Any], settings: Settings) -> str:
    claims = {
        **payload,
        "exp": int((datetime.now(UTC) + timedelta(minutes=settings.access_token_minutes)).timestamp()),
    }
    body = _b64(json.dumps(claims, separators=(",", ":")).encode())
    sig = hmac.new(settings.secret_key.encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64(sig)}"


def decode_access_token(token: str, settings: Settings) -> dict[str, Any] | None:
    try:
        body, sig = token.split(".", 1)
    except ValueError:
        return None
    expected = _b64(hmac.new(settings.secret_key.encode(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    claims = json.loads(_unb64(body))
    if int(claims.get("exp", 0)) < int(datetime.now(UTC).timestamp()):
        return None
    return claims


RAW_DATA_KEYS = {
    "patient",
    "patient_id",
    "patient_name",
    "mrn",
    "dob",
    "ssn",
    "record",
    "records",
    "diagnosis_note",
    "image",
    "dicom",
}


def contains_raw_patient_data(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in RAW_DATA_KEYS:
                return True
            if contains_raw_patient_data(child):
                return True
    if isinstance(value, list):
        return any(contains_raw_patient_data(item) for item in value)
    return False
