from app.services.base import BaseExternalService


class TikTokService(BaseExternalService):
    """Encapsulates TikTok publishing operations."""

    service_name = "tiktok"

    def publish_post(self, payload: dict) -> dict:
        if not payload:
            return {"status": "ignored", "reason": "empty_payload"}
        return self.not_configured("publish_post")
