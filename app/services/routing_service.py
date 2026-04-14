class RoutingService:
    """Determines the next handler for inbound events."""

    _AUDIO_TYPES = {"audio", "voice", "ptt"}
    _TEXT_TYPES = {"text"}

    def route_intent(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            return {
                "status": "invalid_payload",
                "route": "noop",
                "reason": "payload_must_be_dict",
                "payload_received": False,
            }

        platform = str(payload.get("platform") or "unknown").strip().lower()
        message_type = str(payload.get("message_type") or "").strip().lower()
        has_text = bool(payload.get("has_text"))
        has_media = bool(payload.get("has_media"))

        if message_type in self._AUDIO_TYPES and has_media:
            return {
                "status": "ok",
                "route": "transcribe_then_reply",
                "reason": "audio_message_with_media",
                "platform": platform,
                "message_type": message_type,
            }

        if has_text or message_type in self._TEXT_TYPES:
            return {
                "status": "ok",
                "route": "generate_reply",
                "reason": "text_message",
                "platform": platform,
                "message_type": message_type or "text",
            }

        if has_media:
            return {
                "status": "ok",
                "route": "request_text_clarification",
                "reason": "media_without_supported_text_or_audio",
                "platform": platform,
                "message_type": message_type or "media",
            }

        return {
            "status": "ok",
            "route": "noop",
            "reason": "unsupported_or_empty_message",
            "platform": platform,
            "message_type": message_type or "unknown",
        }
