from app.services.base import BaseExternalService


class InstagramService(BaseExternalService):
    """Handles Instagram messaging workflows."""

    service_name = "instagram"

    def process_webhook(self, payload: dict) -> dict:
        if not payload:
            return {"status": "ignored", "reason": "empty_payload"}
        return self.not_configured("process_webhook")
