from app.core.config import settings
from app.services.base import BaseExternalService


class WhatsAppService(BaseExternalService):
    """Handles WhatsApp inbound and outbound messaging workflows."""

    service_name = "whatsapp"

    def _evolution_send_text_url(self) -> str:
        base = settings.evolution_api_base_url.rstrip("/")
        instance_name = settings.evolution_instance_name.strip()
        return f"{base}/message/sendText/{instance_name}"

    def _normalize_recipient_number(self, recipient: str) -> str:
        raw = str(recipient or "").strip()
        if not raw:
            return ""
        if "@" in raw:
            raw = raw.split("@", 1)[0].strip()
        digits = "".join(ch for ch in raw if ch.isdigit())
        return digits or raw

    def send_text_message(self, payload: dict) -> dict:
        to = self._normalize_recipient_number(str(payload.get("to") or "").strip())
        text = str(payload.get("text") or "").strip()
        if not to or not text:
            return self.invalid_payload("send_text_message", "fields 'to' and 'text' are required")
        if not settings.evolution_ready:
            return self.missing_credentials(
                "send_text_message",
                [
                    "EVOLUTION_API_BASE_URL",
                    "EVOLUTION_API_KEY",
                    "EVOLUTION_INSTANCE_NAME",
                ],
            )

        body = {
            "number": to,
            "text": text,
        }
        headers = {
            "apikey": settings.evolution_api_key.strip(),
            "Content-Type": "application/json",
        }
        response = self._request(
            method="POST",
            url=self._evolution_send_text_url(),
            headers=headers,
            json_payload=body,
        )
        if response.get("status") != "ok":
            return response

        body_payload = response.get("body")
        message_id = None
        if isinstance(body_payload, dict):
            key_payload = body_payload.get("key")
            if isinstance(key_payload, dict):
                message_id = key_payload.get("id")
            if message_id is None:
                message_id = body_payload.get("id")

        return {
            "status": "completed",
            "service": self.service_name,
            "action": "send_text_message",
            "message_id": message_id,
            "raw": body_payload,
        }

    def process_webhook(self, payload: dict) -> dict:
        if not payload:
            return {"status": "ignored", "reason": "empty_payload"}

        entries = payload.get("entry")
        if not isinstance(entries, list):
            return self.invalid_payload("process_webhook", "field 'entry' must be a list")

        messages_detected = 0
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for change in entry.get("changes", []):
                if not isinstance(change, dict):
                    continue
                value = change.get("value")
                if not isinstance(value, dict):
                    continue
                messages = value.get("messages")
                if isinstance(messages, list):
                    messages_detected += len(messages)

        return {
            "status": "accepted",
            "service": self.service_name,
            "action": "process_webhook",
            "messages_detected": messages_detected,
        }
