import json

from app.core.config import settings
from app.services.base import BaseExternalService
from app.services.platform_account_service import PlatformAccountService


class InstagramService(BaseExternalService):
    """Handles Instagram messaging workflows."""

    service_name = "instagram"

    def _graph_url(self, object_id: str, edge: str) -> str:
        base = settings.meta_graph_base_url.rstrip("/")
        return f"{base}/{settings.meta_api_version}/{object_id}/{edge}"

    def _resolve_access_token(self, payload: dict) -> str:
        resolved_credentials = PlatformAccountService().resolve_meta_credentials()
        return str(
            payload.get("access_token")
            or resolved_credentials.get("access_token")
            or settings.meta_access_token
        ).strip()

    def _resolve_instagram_business_account_id(self, payload: dict) -> str:
        resolved_credentials = PlatformAccountService().resolve_meta_credentials()
        return str(
            payload.get("instagram_business_account_id")
            or payload.get("ig_user_id")
            or settings.instagram_business_account_id
            or resolved_credentials.get("instagram_business_account_id")
        ).strip()

    def _resolve_page_access_token(
        self,
        *,
        user_access_token: str,
        instagram_business_account_id: str,
    ) -> tuple[str, str | None, dict | None]:
        lookup_result = self._request(
            method="GET",
            url=self._graph_url("me", "accounts"),
            params={
                "fields": "id,name,instagram_business_account{id,username},access_token",
                "access_token": user_access_token,
            },
        )
        if lookup_result.get("status") != "ok":
            return "", None, lookup_result

        body = lookup_result.get("body")
        if not isinstance(body, dict):
            return "", None, self.request_failed(
                "resolve_page_access_token",
                "Meta page lookup returned invalid body",
            )

        target_ig_id = str(instagram_business_account_id or "").strip()
        data = body.get("data")
        if not isinstance(data, list):
            return "", None, self.request_failed(
                "resolve_page_access_token",
                "Meta page lookup returned invalid data list",
            )

        fallback_page_token = ""
        fallback_page_id = None
        for item in data:
            if not isinstance(item, dict):
                continue
            page_access_token = str(item.get("access_token") or "").strip()
            page_id = str(item.get("id") or "").strip() or None
            if page_access_token and not fallback_page_token:
                fallback_page_token = page_access_token
                fallback_page_id = page_id

            ig_payload = item.get("instagram_business_account")
            ig_id = str(ig_payload.get("id") or "").strip() if isinstance(ig_payload, dict) else ""
            if target_ig_id and ig_id == target_ig_id and page_access_token:
                return page_access_token, page_id, None

        if fallback_page_token:
            return fallback_page_token, fallback_page_id, None
        return "", None, self.request_failed(
            "resolve_page_access_token",
            "Could not resolve page access token for instagram account",
        )

    def send_text_message(self, payload: dict) -> dict:
        if not settings.meta_enabled:
            return self.integration_disabled("send_text_message", "meta_disabled")

        recipient_id = str(payload.get("to") or "").strip()
        text = str(payload.get("text") or "").strip()
        if not recipient_id or not text:
            return self.invalid_payload("send_text_message", "fields 'to' and 'text' are required")

        instagram_business_account_id = self._resolve_instagram_business_account_id(payload)
        user_access_token = self._resolve_access_token(payload)
        if not instagram_business_account_id or not user_access_token:
            return self.missing_credentials(
                "send_text_message",
                [
                    "INSTAGRAM_BUSINESS_ACCOUNT_ID (or OAuth metadata)",
                    "META_ACCESS_TOKEN (or OAuth stored token)",
                ],
            )
        page_access_token, page_id, page_token_error = self._resolve_page_access_token(
            user_access_token=user_access_token,
            instagram_business_account_id=instagram_business_account_id,
        )
        if not page_access_token:
            if isinstance(page_token_error, dict):
                return page_token_error
            return self.request_failed(
                "send_text_message",
                "Could not resolve page access token",
            )

        response = self._request(
            method="POST",
            url=self._graph_url(instagram_business_account_id, "messages"),
            form_payload={
                "recipient": json.dumps({"id": recipient_id}, separators=(",", ":")),
                "message": json.dumps({"text": text}, separators=(",", ":")),
                "access_token": page_access_token,
            },
        )
        if response.get("status") != "ok":
            return response

        body_payload = response.get("body")
        message_id = None
        if isinstance(body_payload, dict):
            message_id = body_payload.get("message_id")

        return {
            "status": "completed",
            "service": self.service_name,
            "action": "send_text_message",
            "message_id": message_id,
            "page_id": page_id,
            "raw": body_payload,
        }

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
