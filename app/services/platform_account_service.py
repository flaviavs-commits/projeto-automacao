from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import decrypt_secret, encrypt_secret
from app.models.platform_account import PlatformAccount


class PlatformAccountService:
    """Reads persisted OAuth credentials for platform integrations."""

    _TOKEN_EXPIRY_SAFETY_WINDOW_SECONDS = 60
    _TOKEN_REFRESH_WINDOW_SECONDS = 24 * 60 * 60

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

    def _is_within_refresh_window(self, token_expires_at: datetime | None) -> bool:
        if token_expires_at is None:
            return False

        expires_at = token_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        else:
            expires_at = expires_at.astimezone(timezone.utc)
        now_utc = datetime.now(timezone.utc)
        refresh_window = timedelta(seconds=self._TOKEN_REFRESH_WINDOW_SECONDS)
        return expires_at <= (now_utc + refresh_window)

    def _exchange_for_long_lived_token(self, access_token: str) -> dict:
        app_id = settings.effective_meta_app_id.strip()
        app_secret = settings.effective_meta_app_secret.strip()
        if not app_id or not app_secret:
            return {"status": "skipped", "reason": "missing_meta_app_credentials"}

        graph_base = settings.meta_graph_base_url.rstrip("/")
        url = f"{graph_base}/{settings.meta_api_version}/oauth/access_token"
        params = {
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": access_token,
        }
        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.get(url, params=params)
                body = response.json()
        except Exception as exc:  # noqa: BLE001
            return {"status": "failed", "reason": f"{exc.__class__.__name__}: {exc}"}

        if response.status_code < 200 or response.status_code >= 300:
            return {
                "status": "failed",
                "status_code": response.status_code,
                "body": body if isinstance(body, dict) else {"raw": str(body)},
            }

        if not isinstance(body, dict):
            return {"status": "failed", "reason": "invalid_response_body"}
        token = str(body.get("access_token") or "").strip()
        if not token:
            return {"status": "failed", "reason": "missing_access_token"}
        expires_in = body.get("expires_in")
        return {
            "status": "ok",
            "access_token": token,
            "expires_in": int(expires_in) if isinstance(expires_in, (int, float, str)) and str(expires_in).isdigit() else None,
        }

    def _refresh_latest_meta_token_if_needed(self) -> dict:
        try:
            with SessionLocal() as db:
                account = (
                    db.query(PlatformAccount)
                    .filter(PlatformAccount.platform == "meta")
                    .order_by(PlatformAccount.updated_at.desc())
                    .first()
                )
                if account is None:
                    return {"status": "skipped", "reason": "account_not_found"}

                encrypted_token = str(account.access_token_encrypted or "").strip()
                current_token = decrypt_secret(
                    encrypted_token,
                    secret=settings.effective_token_encryption_secret,
                )
                current_token = str(current_token or "").strip()
                if not current_token:
                    return {"status": "skipped", "reason": "missing_decrypted_token"}

                token_expired = self._is_meta_token_expired(account.token_expires_at)
                in_refresh_window = self._is_within_refresh_window(account.token_expires_at)
                if not token_expired and not in_refresh_window:
                    return {"status": "skipped", "reason": "token_still_fresh"}

                exchange_result = self._exchange_for_long_lived_token(current_token)
                if exchange_result.get("status") != "ok":
                    return {
                        "status": "failed",
                        "reason": "exchange_failed",
                        "exchange": exchange_result,
                    }

                new_access_token = str(exchange_result.get("access_token") or "").strip()
                if not new_access_token:
                    return {"status": "failed", "reason": "empty_new_token"}

                encrypted_new = encrypt_secret(
                    new_access_token,
                    secret=settings.effective_token_encryption_secret,
                )
                account.access_token_encrypted = encrypted_new

                expires_in = exchange_result.get("expires_in")
                if isinstance(expires_in, int) and expires_in > 0:
                    account.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

                metadata = account.metadata_json if isinstance(account.metadata_json, dict) else {}
                account.metadata_json = {
                    **metadata,
                    "oauth_token_source": "long_lived_refreshed",
                    "oauth_refreshed_at": datetime.now(timezone.utc).isoformat(),
                }
                db.commit()
                db.refresh(account)
                return {
                    "status": "ok",
                    "platform_account_id": str(account.id),
                    "token_expires_at": (
                        account.token_expires_at.isoformat() if account.token_expires_at is not None else None
                    ),
                }
        except Exception as exc:  # noqa: BLE001
            return {"status": "failed", "reason": f"{exc.__class__.__name__}: {exc}"}

    def get_latest_meta_snapshot(self) -> dict:
        refresh_result = self._refresh_latest_meta_token_if_needed()
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
                "refresh_attempt": refresh_result,
            }

        if account is None:
            return {
                "account_found": False,
                "token_present": False,
                "token_expired": False,
                "token_usable": False,
                "instagram_account_ready": False,
                "token_expires_at": None,
                "refresh_attempt": refresh_result,
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
        whatsapp_business_account_id = (
            str(metadata.get("whatsapp_business_account_id") or "").strip() or None
        )
        whatsapp_phone_number_id = str(metadata.get("whatsapp_phone_number_id") or "").strip() or None
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
            "whatsapp_business_account_id": whatsapp_business_account_id,
            "whatsapp_phone_number_id": whatsapp_phone_number_id,
            "whatsapp_phone_number_ready": bool(whatsapp_phone_number_id),
            "token_expires_at": (
                account.token_expires_at.isoformat() if account.token_expires_at is not None else None
            ),
            "refresh_attempt": refresh_result,
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
            "whatsapp_phone_number_id": snapshot.get("whatsapp_phone_number_id"),
            "token_expires_at": snapshot.get("token_expires_at"),
        }

    def resolve_meta_credentials(
        self,
        *,
        preferred_phone_number_id: str | None = None,
    ) -> dict:
        snapshot = self.get_latest_meta_snapshot()
        env_access_token = settings.meta_access_token.strip()
        env_phone_number_id = settings.meta_whatsapp_phone_number_id.strip()

        resolved_token = ""
        token_source = ""
        if snapshot.get("token_usable"):
            resolved_token = str(snapshot.get("access_token") or "").strip()
            token_source = "oauth_persisted"
        elif env_access_token:
            resolved_token = env_access_token
            token_source = "env_meta_access_token"

        resolved_phone = (
            str(preferred_phone_number_id or "").strip()
            or env_phone_number_id
            or str(snapshot.get("whatsapp_phone_number_id") or "").strip()
        )

        return {
            "access_token": resolved_token,
            "access_token_source": token_source or "missing",
            "phone_number_id": resolved_phone,
            "instagram_business_account_id": snapshot.get("instagram_business_account_id"),
            "token_usable": bool(snapshot.get("token_usable")),
            "token_present": bool(snapshot.get("token_present")),
            "token_expired": bool(snapshot.get("token_expired")),
            "token_expires_at": snapshot.get("token_expires_at"),
            "platform_account_id": snapshot.get("platform_account_id"),
            "refresh_attempt": snapshot.get("refresh_attempt"),
        }
