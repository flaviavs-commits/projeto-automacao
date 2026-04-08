from app.services.base import BaseExternalService


class InstagramPublishService(BaseExternalService):
    """Encapsulates Instagram publishing operations."""

    service_name = "instagram_publish"

    def publish_post(self, payload: dict) -> dict:
        if not payload:
            return {"status": "ignored", "reason": "empty_payload"}
        return self.not_configured("publish_post")
