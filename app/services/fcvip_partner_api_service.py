from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.services.base import BaseExternalService, ExternalServiceResult
from app.services.customer_data_provider import CustomerDataProvider


class FCVIPPartnerAPIService(BaseExternalService, CustomerDataProvider):
    """Reads customer signals from FC VIP Partner API without local persistence."""

    service_name = "fcvip_partner_api"

    def lookup_customer_by_whatsapp(self, *, phone_number: str) -> ExternalServiceResult:
        action = "lookup_customer_by_whatsapp"
        normalized_phone = self._normalize_phone_number(phone_number)
        if not normalized_phone:
            return self.invalid_payload(action, "phone_number is required")
        if not settings.fcvip_partner_api_enabled:
            return self.integration_disabled(action, "fcvip_partner_api_disabled")

        missing_required: list[str] = []
        if not settings.fcvip_partner_api_base_url.strip():
            missing_required.append("FCVIP_PARTNER_API_BASE_URL")
        if not settings.fcvip_partner_api_key.strip():
            missing_required.append("FCVIP_PARTNER_API_KEY")
        if missing_required:
            return self.missing_credentials(action, missing_required)

        page_size = max(1, min(200, int(settings.fcvip_partner_api_page_size)))
        max_pages = max(1, int(settings.fcvip_partner_api_leads_max_pages))
        endpoint = f"{settings.fcvip_partner_api_base_url.rstrip('/')}/api/partner/leads/"

        for page in range(1, max_pages + 1):
            response = self._request(
                method="GET",
                url=endpoint,
                headers=self._auth_headers(),
                params={"page": page, "page_size": page_size},
                timeout_seconds=max(1.0, float(settings.fcvip_partner_api_timeout_seconds)),
            )
            if response.get("status") != "ok":
                return ExternalServiceResult(
                    status=response.get("status"),
                    service=self.service_name,
                    action=action,
                    detail=response.get("detail"),
                    status_code=response.get("status_code"),
                    checked_pages=page,
                )

            leads_payload = self._extract_leads_payload(response.get("body"))
            if leads_payload is None:
                return self.request_failed(action, "invalid_partner_envelope")

            for lead in leads_payload:
                lead_phone = self._extract_lead_phone(lead)
                if not lead_phone:
                    continue
                if self._phone_matches(normalized_phone, lead_phone):
                    return ExternalServiceResult(
                        status="completed",
                        service=self.service_name,
                        action=action,
                        customer_exists=True,
                        customer_status="antigo",
                        matched_lead_id=lead.get("id"),
                        checked_pages=page,
                    )

            total_pages = self._extract_total_pages(response.get("body"))
            if total_pages is not None and page >= total_pages:
                break

        return ExternalServiceResult(
            status="completed",
            service=self.service_name,
            action=action,
            customer_exists=False,
            customer_status="novo",
            checked_pages=max_pages,
        )

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Api-Key {settings.fcvip_partner_api_key.strip()}",
            "Content-Type": "application/json",
        }

    def _extract_leads_payload(self, body: Any) -> list[dict[str, Any]] | None:
        if not isinstance(body, dict):
            return None
        data_payload = body.get("data")
        if not isinstance(data_payload, dict):
            return None
        rows = data_payload.get("leads")
        if not isinstance(rows, list):
            return None
        return [row for row in rows if isinstance(row, dict)]

    def _extract_total_pages(self, body: Any) -> int | None:
        if not isinstance(body, dict):
            return None
        data_payload = body.get("data")
        if not isinstance(data_payload, dict):
            return None
        raw_total_pages = data_payload.get("total_pages")
        try:
            parsed = int(raw_total_pages)
        except Exception:  # noqa: BLE001
            return None
        return parsed if parsed > 0 else None

    def _extract_lead_phone(self, lead_payload: dict[str, Any]) -> str:
        for key in ("whatsapp", "telefone", "phone"):
            raw_value = lead_payload.get(key)
            normalized = self._normalize_phone_number(str(raw_value or ""))
            if normalized:
                return normalized
        return ""

    def _normalize_phone_number(self, value: str) -> str:
        digits = "".join(ch for ch in str(value or "") if ch.isdigit())
        return digits

    def _phone_matches(self, source_phone: str, candidate_phone: str) -> bool:
        if source_phone == candidate_phone:
            return True
        if len(source_phone) >= 10 and len(candidate_phone) >= 10:
            return source_phone[-10:] == candidate_phone[-10:]
        return False
