from app.core.config import settings
from app.services.base import BaseExternalService


class WhatsAppService(BaseExternalService):
    """Handles WhatsApp inbound and outbound messaging workflows."""

    service_name = "whatsapp"

    def _evolution_send_text_url(self) -> str:
        base = settings.evolution_api_base_url.rstrip("/")
        instance_name = settings.evolution_instance_name.strip()
        return f"{base}/message/sendText/{instance_name}"

    def _evolution_connection_state_url(self) -> str:
        base = settings.evolution_api_base_url.rstrip("/")
        instance_name = settings.evolution_instance_name.strip()
        return f"{base}/instance/connectionState/{instance_name}"

    def _evolution_connect_url(self) -> str:
        base = settings.evolution_api_base_url.rstrip("/")
        instance_name = settings.evolution_instance_name.strip()
        return f"{base}/instance/connect/{instance_name}"

    def _evolution_headers(self) -> dict[str, str]:
        return {
            "apikey": settings.evolution_api_key.strip(),
            "Content-Type": "application/json",
        }

    def _normalize_recipient_number(self, recipient: str) -> str:
        raw = str(recipient or "").strip()
        if not raw:
            return ""
        if "@" in raw:
            raw = raw.split("@", 1)[0].strip()
        digits = "".join(ch for ch in raw if ch.isdigit())
        return digits or raw

    def _extract_message_id(self, body_payload: dict | None) -> str | None:
        if not isinstance(body_payload, dict):
            return None
        key_payload = body_payload.get("key")
        if isinstance(key_payload, dict):
            message_id = key_payload.get("id")
            if message_id:
                return str(message_id)
        raw_message_id = body_payload.get("id")
        return str(raw_message_id) if raw_message_id else None

    def _should_attempt_reconnect(self, response: dict) -> bool:
        if response.get("status") != "request_failed":
            return False
        status_code = response.get("status_code")
        if status_code is not None and status_code not in {408, 409, 500, 502, 503, 504}:
            return False
        detail = str(response.get("detail") or "").lower()
        reconnect_markers = (
            "connection closed",
            "timed out",
            "readtimeout",
            "not connected",
            "instance is not connected",
        )
        return any(marker in detail for marker in reconnect_markers)

    def _extract_connection_state(self, payload: dict) -> str | None:
        if not isinstance(payload, dict):
            return None
        instance_payload = payload.get("instance")
        if isinstance(instance_payload, dict):
            state = instance_payload.get("state")
            if state:
                return str(state).strip().lower()
        state = payload.get("state")
        if state:
            return str(state).strip().lower()
        return None

    def _attempt_reconnect(self) -> dict:
        headers = self._evolution_headers()
        state_result = self._request(
            method="GET",
            url=self._evolution_connection_state_url(),
            headers=headers,
            timeout_seconds=15.0,
        )
        current_state = None
        if state_result.get("status") == "ok":
            current_state = self._extract_connection_state(state_result.get("body") or {})
            if current_state == "open":
                return {"status": "already_open", "state": current_state}

        connect_result = self._request(
            method="GET",
            url=self._evolution_connect_url(),
            headers=headers,
            timeout_seconds=30.0,
        )
        if connect_result.get("status") != "ok":
            return {
                "status": "connect_failed",
                "state": current_state,
                "detail": connect_result.get("detail"),
                "status_code": connect_result.get("status_code"),
            }

        connect_body = connect_result.get("body") if isinstance(connect_result.get("body"), dict) else {}
        return {
            "status": "connect_triggered",
            "state": current_state,
            "has_qr": bool(connect_body.get("base64")),
            "has_pairing_code": bool(connect_body.get("pairingCode")),
        }

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
        headers = self._evolution_headers()
        response = self._request(
            method="POST",
            url=self._evolution_send_text_url(),
            headers=headers,
            json_payload=body,
        )
        reconnect_attempt = None
        retried = False
        if response.get("status") != "ok" and self._should_attempt_reconnect(response):
            reconnect_attempt = self._attempt_reconnect()
            retried = True
            response = self._request(
                method="POST",
                url=self._evolution_send_text_url(),
                headers=headers,
                json_payload=body,
            )
            if response.get("status") != "ok":
                failed_response = dict(response)
                failed_response["retried"] = retried
                failed_response["reconnect_attempt"] = reconnect_attempt
                return failed_response

        if response.get("status") != "ok":
            return response

        body_payload = response.get("body")
        message_id = self._extract_message_id(body_payload if isinstance(body_payload, dict) else None)

        result = {
            "status": "completed",
            "service": self.service_name,
            "action": "send_text_message",
            "message_id": message_id,
            "raw": body_payload,
        }
        if retried:
            result["retried"] = True
            result["reconnect_attempt"] = reconnect_attempt
        return result

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
