from app.services.base import BaseExternalService


class WhatsAppService(BaseExternalService):
    """Handles WhatsApp inbound and outbound messaging workflows."""

    service_name = "whatsapp"

    def process_webhook(self, payload: dict) -> dict:
        if not payload:
            return {"status": "ignored", "reason": "empty_payload"}
        return self.not_configured("process_webhook")
