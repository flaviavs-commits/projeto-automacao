from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import decrypt_secret
from app.models.platform_account import PlatformAccount


class PlatformAccountService:
    """Reads persisted OAuth credentials for platform integrations."""

    _TOKEN_EXPIRY_SAFETY_WINDOW_SECONDS = 60

    def _is_meta_token_expired(self, token_expires_at: datetime | None) -> bool:
        if token_expires_at is None:
            return False

        expires_at = token_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        else:
            expires_at = expires_at.astimezone(timezone.utc)

        now_utc = datetime.now(timezone.utc)
        safety_window = timedelta(seconds=self._TOKEN_EXPIRY_SAFETY_WINDOW_SECONDS)
        return expires_at <= (now_utc + safety_window)

    def get_latest_meta_snapshot(self) -> dict:
        try:
            with SessionLocal() as db:
                account = (
                    db.query(PlatformAccount)
                    .filter(PlatformAccount.platform == "meta")
                    .order_by(PlatformAccount.updated_at.desc())
                    .first()
                )
        except Exception:  # noqa: BLE001
            return {
                "account_found": False,
                "token_present": False,
                "token_expired": False,
                "token_usable": False,
                "instagram_account_ready": False,
                "token_expires_at": None,
            }

        if account is None:
            return {
                "account_found": False,
                "token_present": False,
                "token_expired": False,
                "token_usable": False,
                "instagram_account_ready": False,
                "token_expires_at": None,
            }

        encrypted_token = str(account.access_token_encrypted or "").strip()
        access_token = decrypt_secret(
            encrypted_token,
            secret=settings.effective_token_encryption_secret,
        )
        metadata = account.metadata_json if isinstance(account.metadata_json, dict) else {}
        instagram_business_account_id = (
            str(metadata.get("instagram_business_account_id") or "").strip() or None
        )
        token_present = bool(str(access_token or "").strip())
        token_expired = self._is_meta_token_expired(account.token_expires_at) if token_present else False
        token_usable = token_present and not token_expired

        return {
            "account_found": True,
            "platform_account_id": str(account.id),
            "external_account_id": account.external_account_id,
            "access_token": access_token if token_usable else "",
            "token_present": token_present,
            "token_expired": token_expired,
            "token_usable": token_usable,
            "instagram_business_account_id": instagram_business_account_id,
            "instagram_account_ready": bool(instagram_business_account_id),
            "token_expires_at": (
                account.token_expires_at.isoformat() if account.token_expires_at is not None else None
            ),
        }

    def get_latest_meta_credentials(self) -> dict:
        snapshot = self.get_latest_meta_snapshot()
        if not snapshot.get("token_usable"):
            return {}

        return {
            "platform_account_id": snapshot.get("platform_account_id"),
            "external_account_id": snapshot.get("external_account_id"),
            "access_token": str(snapshot.get("access_token") or ""),
            "instagram_business_account_id": snapshot.get("instagram_business_account_id"),
            "token_expires_at": snapshot.get("token_expires_at"),
        }
