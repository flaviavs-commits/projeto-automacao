import json
from typing import Any

import httpx


class ExternalServiceResult(dict):
    """Simple explicit response shape for integration calls."""


class BaseExternalService:
    """Base helper for integrations that should not call external APIs without credentials."""

    service_name = "external_service"

    def not_configured(self, action: str) -> ExternalServiceResult:
        return ExternalServiceResult(
            status="not_configured",
            service=self.service_name,
            action=action,
        )

    def integration_disabled(self, action: str, reason: str) -> ExternalServiceResult:
        return ExternalServiceResult(
            status="integration_disabled",
            service=self.service_name,
            action=action,
            reason=reason,
        )

    def missing_credentials(self, action: str, required: list[str]) -> ExternalServiceResult:
        return ExternalServiceResult(
            status="missing_credentials",
            service=self.service_name,
            action=action,
            required=required,
        )

    def invalid_payload(self, action: str, detail: str) -> ExternalServiceResult:
        return ExternalServiceResult(
            status="invalid_payload",
            service=self.service_name,
            action=action,
            detail=detail,
        )

    def request_failed(
        self,
        action: str,
        detail: str,
        status_code: int | None = None,
        *,
        error_meta: dict[str, Any] | None = None,
    ) -> ExternalServiceResult:
        payload: dict[str, Any] = {
            "status": "request_failed",
            "service": self.service_name,
            "action": action,
            "detail": detail,
        }
        if status_code is not None:
            payload["status_code"] = status_code
        if error_meta:
            payload["error_meta"] = error_meta
        return ExternalServiceResult(**payload)

    def _extract_error_meta(self, body: Any) -> dict[str, Any]:
        if not isinstance(body, dict):
            return {}
        error = body.get("error")
        if not isinstance(error, dict):
            return {}
        return {
            "type": error.get("type"),
            "code": error.get("code"),
            "error_subcode": error.get("error_subcode") or error.get("subcode"),
            "message": error.get("message"),
            "fbtrace_id": error.get("fbtrace_id"),
        }

    def _decode_response_body(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except Exception:  # noqa: BLE001
            text = response.text
            if len(text) <= 1000:
                return text
            return text[:1000] + "...(truncated)"

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json_payload: dict | None = None,
        form_payload: dict | None = None,
        params: dict | None = None,
        timeout_seconds: float = 20.0,
    ) -> ExternalServiceResult:
        try:
            with httpx.Client(timeout=timeout_seconds) as client:
                response = client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=json_payload,
                    data=form_payload,
                    params=params,
                )
        except Exception as exc:  # noqa: BLE001
            return self.request_failed(
                action=method.lower(),
                detail=f"{exc.__class__.__name__}: {exc}",
            )

        body = self._decode_response_body(response)
        if 200 <= response.status_code < 300:
            return ExternalServiceResult(
                status="ok",
                service=self.service_name,
                status_code=response.status_code,
                body=body,
            )

        body_text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=True)
        error_meta = self._extract_error_meta(body)
        return self.request_failed(
            action=method.lower(),
            detail=body_text[:1000],
            status_code=response.status_code,
            error_meta=error_meta or None,
        )
