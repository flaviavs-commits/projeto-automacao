import base64
import json
import re
from datetime import datetime, timezone
from hashlib import sha1, sha256
from hmac import new as hmac_new
from secrets import compare_digest

from cryptography.fernet import Fernet, InvalidToken


def safe_compare(value: str, expected: str) -> bool:
    if not value or not expected:
        return False
    return compare_digest(value, expected)


def _escape_char_as_unicode(char: str) -> str:
    codepoint = ord(char)
    if codepoint <= 0xFFFF:
        return f"\\u{codepoint:04x}"

    # Encode supplementary chars (e.g. emoji) as surrogate pairs.
    codepoint -= 0x10000
    high = 0xD800 + (codepoint >> 10)
    low = 0xDC00 + (codepoint & 0x3FF)
    return f"\\u{high:04x}\\u{low:04x}"


def _escape_meta_payload(body: bytes, *, include_legacy_ascii_escapes: bool) -> bytes:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return body

    chunks: list[str] = []
    for char in text:
        if ord(char) > 127:
            chunks.append(_escape_char_as_unicode(char))
            continue

        if include_legacy_ascii_escapes:
            if char == "/":
                chunks.append("\\/")
                continue
            if char == "<":
                chunks.append("\\u003c")
                continue
            if char == ">":
                chunks.append("\\u003e")
                continue
            if char == "%":
                chunks.append("\\u0025")
                continue
            if char == "@":
                chunks.append("\\u0040")
                continue

        chunks.append(char)

    return "".join(chunks).encode("utf-8")


def _candidate_signature_payloads(body: bytes) -> list[bytes]:
    candidates = [body]
    escaped_unicode = _escape_meta_payload(body, include_legacy_ascii_escapes=False)
    escaped_extended = _escape_meta_payload(body, include_legacy_ascii_escapes=True)

    for payload in (escaped_unicode, escaped_extended):
        if payload not in candidates:
            candidates.append(payload)
    return candidates


def _extract_signature_digest(raw_digest: str) -> str | None:
    candidate = str(raw_digest or "").strip().strip('"').strip("'").lower()
    if not candidate:
        return None

    # Some senders include additional metadata after the digest (e.g. ",sha1=...").
    for delimiter in (",", ";", " "):
        if delimiter in candidate:
            candidate = candidate.split(delimiter, 1)[0].strip()

    match = re.fullmatch(r"[0-9a-f]+", candidate)
    if not match:
        return None
    return candidate


def verify_meta_signature(*, body: bytes, signature_header: str | None, app_secret: str) -> bool:
    secret = str(app_secret or "").strip()
    if not secret:
        return True

    provided = str(signature_header or "").strip()
    if not provided or "=" not in provided:
        return False

    algo, provided_digest = provided.split("=", 1)
    normalized_algo = algo.strip().lower()
    if normalized_algo not in {"sha1", "sha256"}:
        return False
    if not provided_digest:
        return False

    digest_impl = sha256 if normalized_algo == "sha256" else sha1
    normalized_digest = _extract_signature_digest(provided_digest)
    if normalized_digest is None:
        return False
    for candidate_body in _candidate_signature_payloads(body):
        expected_digest = hmac_new(secret.encode("utf-8"), candidate_body, digest_impl).hexdigest()
        if compare_digest(normalized_digest, expected_digest.lower()):
            return True
    return False


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
