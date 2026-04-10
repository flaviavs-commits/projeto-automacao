from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import decrypt_secret
from app.models.platform_account import PlatformAccount


class PlatformAccountService:
    """Reads persisted OAuth credentials for platform integrations."""

    def get_latest_meta_credentials(self) -> dict:
        try:
            with SessionLocal() as db:
                account = (
                    db.query(PlatformAccount)
                    .filter(PlatformAccount.platform == "meta")
                    .order_by(PlatformAccount.updated_at.desc())
                    .first()
                )
        except Exception:  # noqa: BLE001
            return {}

        if account is None:
            return {}

        encrypted_token = str(account.access_token_encrypted or "").strip()
        access_token = decrypt_secret(
            encrypted_token,
            secret=settings.effective_token_encryption_secret,
        )
        if access_token is None:
            return {}

        metadata = account.metadata_json if isinstance(account.metadata_json, dict) else {}
        ig_business_account_id = str(metadata.get("instagram_business_account_id") or "").strip() or None

        return {
            "platform_account_id": str(account.id),
            "external_account_id": account.external_account_id,
            "access_token": access_token,
            "instagram_business_account_id": ig_business_account_id,
            "token_expires_at": (
                account.token_expires_at.isoformat() if account.token_expires_at is not None else None
            ),
        }
