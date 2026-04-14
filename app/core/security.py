import base64
import json
from datetime import datetime, timezone
from hashlib import sha256
from hmac import new as hmac_new
from secrets import compare_digest

from cryptography.fernet import Fernet, InvalidToken


def safe_compare(value: str, expected: str) -> bool:
    if not value or not expected:
        return False
    return compare_digest(value, expected)


def verify_meta_signature(*, body: bytes, signature_header: str | None, app_secret: str) -> bool:
    secret = str(app_secret or "").strip()
    if not secret:
        return True

    provided = str(signature_header or "").strip()
    if not provided or "=" not in provided:
        return False

    algo, provided_digest = provided.split("=", 1)
    if algo.strip().lower() != "sha256":
        return False
    if not provided_digest:
        return False

    expected_digest = hmac_new(secret.encode("utf-8"), body, sha256).hexdigest()
    return compare_digest(provided_digest.strip().lower(), expected_digest.lower())


def _derive_fernet(secret: str) -> Fernet:
    normalized = secret.strip()
    if not normalized:
        raise ValueError("secret is required")
    key = base64.urlsafe_b64encode(sha256(normalized.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_secret(value: str, *, secret: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return _derive_fernet(secret).encrypt(text.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str, *, secret: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        decrypted = _derive_fernet(secret).decrypt(text.encode("utf-8"))
        return decrypted.decode("utf-8")
    except InvalidToken:
        return None


def _urlsafe_b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _urlsafe_b64decode(raw: str) -> bytes:
    padded = raw + "=" * ((4 - len(raw) % 4) % 4)
    return base64.urlsafe_b64decode(padded.encode("utf-8"))


def sign_state_payload(payload: dict, *, secret: str) -> str:
    serialized = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    encoded_payload = _urlsafe_b64encode(serialized.encode("utf-8"))
    signature = hmac_new(
        secret.encode("utf-8"),
        encoded_payload.encode("utf-8"),
        sha256,
    ).hexdigest()
    return f"{encoded_payload}.{signature}"


def verify_state_payload(signed_payload: str, *, secret: str) -> dict | None:
    token = str(signed_payload or "").strip()
    if not token or "." not in token:
        return None

    encoded_payload, signature = token.rsplit(".", 1)
    expected_signature = hmac_new(
        secret.encode("utf-8"),
        encoded_payload.encode("utf-8"),
        sha256,
    ).hexdigest()
    if not compare_digest(signature, expected_signature):
        return None

    try:
        raw_payload = _urlsafe_b64decode(encoded_payload)
        parsed = json.loads(raw_payload.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None

    if not isinstance(parsed, dict):
        return None
    return parsed


def is_state_payload_fresh(
    payload: dict,
    *,
    max_age_seconds: int,
    now: datetime | None = None,
) -> bool:
    iat = payload.get("iat")
    if not isinstance(iat, int):
        return False
    if max_age_seconds <= 0:
        return False

    now_utc = now or datetime.now(timezone.utc)
    now_ts = int(now_utc.timestamp())
    # Reject timestamps too far in the future.
    if iat > now_ts + 60:
        return False
    return (now_ts - iat) <= max_age_seconds
