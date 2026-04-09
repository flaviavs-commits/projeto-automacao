from app.core.config import settings
from app.services.base import BaseExternalService


class WhatsAppService(BaseExternalService):
    """Handles WhatsApp inbound and outbound messaging workflows."""

    service_name = "whatsapp"

    def _messages_url(self, phone_number_id: str) -> str:
        base = settings.meta_graph_base_url.rstrip("/")
        return f"{base}/{settings.meta_api_version}/{phone_number_id}/messages"

    def send_text_message(self, payload: dict) -> dict:
        to = str(payload.get("to") or "").strip()
        text = str(payload.get("text") or "").strip()
        if not to or not text:
            return self.invalid_payload("send_text_message", "fields 'to' and 'text' are required")

        access_token = str(payload.get("access_token") or settings.meta_access_token).strip()
        phone_number_id = str(
            payload.get("phone_number_id")
            or settings.meta_whatsapp_phone_number_id
        ).strip()
        if not access_token or not phone_number_id:
            return self.missing_credentials(
                "send_text_message",
                ["META_ACCESS_TOKEN", "META_WHATSAPP_PHONE_NUMBER_ID"],
            )

        body = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {
                "body": text,
                "preview_url": bool(payload.get("preview_url", False)),
            },
        }
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        response = self._request(
            method="POST",
            url=self._messages_url(phone_number_id),
            headers=headers,
            json_payload=body,
        )
        if response.get("status") != "ok":
            return response

        body_payload = response.get("body")
        message_id = None
        if isinstance(body_payload, dict):
            messages = body_payload.get("messages")
            if isinstance(messages, list) and messages:
                first = messages[0]
                if isinstance(first, dict):
                    message_id = first.get("id")

        return {
            "status": "sent",
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
