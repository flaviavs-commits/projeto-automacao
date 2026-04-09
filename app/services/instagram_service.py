from app.services.base import BaseExternalService


class InstagramService(BaseExternalService):
    """Handles Instagram messaging workflows."""

    service_name = "instagram"

    def process_webhook(self, payload: dict) -> dict:
        if not payload:
            return {"status": "ignored", "reason": "empty_payload"}

        entries = payload.get("entry")
        if not isinstance(entries, list):
            return self.invalid_payload("process_webhook", "field 'entry' must be a list")

        events_detected = 0
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            messaging = entry.get("messaging")
            if isinstance(messaging, list):
                events_detected += len(messaging)

        return {
            "status": "accepted",
            "service": self.service_name,
            "action": "process_webhook",
            "events_detected": events_detected,
        }
