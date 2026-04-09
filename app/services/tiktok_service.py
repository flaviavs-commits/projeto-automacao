from app.core.config import settings
from app.services.base import BaseExternalService


class TikTokService(BaseExternalService):
    """Encapsulates TikTok publishing operations."""

    service_name = "tiktok"

    def publish_post(self, payload: dict) -> dict:
        if not payload:
            return {"status": "ignored", "reason": "empty_payload"}

        access_token = str(payload.get("access_token") or "").strip()
        api_url = str(payload.get("api_url") or "").strip()
        if not api_url:
            api_path = str(payload.get("api_path") or "").strip()
            if api_path:
                api_url = f"{settings.tiktok_api_base_url.rstrip('/')}/{api_path.lstrip('/')}"

        if not access_token or not api_url:
            return self.missing_credentials(
                "publish_post",
                ["access_token", "api_url (or api_path + TIKTOK_API_BASE_URL)"],
            )

        body = payload.get("body")
        if body is not None and not isinstance(body, dict):
            return self.invalid_payload("publish_post", "field 'body' must be a JSON object when provided")

        response = self._request(
            method="POST",
            url=api_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json_payload=body or {},
        )
        if response.get("status") != "ok":
            return response

        return {
            "status": "published",
            "service": self.service_name,
            "action": "publish_post",
            "raw": response.get("body"),
        }
