from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.audit_log import AuditLog
from app.services.base import BaseExternalService
from app.services.platform_account_service import PlatformAccountService


class MetaLiveService(BaseExternalService):
    """Executes live health probes against Meta outbound/inbound flows."""

    service_name = "meta_live"

    def _graph_url(self, path: str) -> str:
        base = settings.meta_graph_base_url.rstrip("/")
        return f"{base}/{settings.meta_api_version}/{path.lstrip('/')}"

    def _public_credentials_view(self, resolved: dict[str, Any]) -> dict[str, Any]:
        token = str(resolved.get("access_token") or "").strip()
        return {
            "access_token_source": resolved.get("access_token_source"),
            "access_token_present": bool(token),
            "access_token_suffix": token[-6:] if token else "",
            "phone_number_id": resolved.get("phone_number_id"),
            "instagram_business_account_id": resolved.get("instagram_business_account_id"),
            "token_usable": resolved.get("token_usable"),
            "token_present": resolved.get("token_present"),
            "token_expired": resolved.get("token_expired"),
            "token_expires_at": resolved.get("token_expires_at"),
            "platform_account_id": resolved.get("platform_account_id"),
            "refresh_attempt": resolved.get("refresh_attempt"),
        }

    def probe_outbound(self) -> dict[str, Any]:
        if not settings.meta_enabled:
            return {
                "status": "integration_disabled",
                "where": "settings.meta_enabled",
                "message": "Meta desabilitado por configuracao",
            }

        resolved = PlatformAccountService().resolve_meta_credentials()
        token = str(resolved.get("access_token") or "").strip()
        phone_number_id = str(resolved.get("phone_number_id") or "").strip()
        if not token:
            return {
                "status": "missing_credentials",
                "where": "token",
                "message": "Sem token de acesso valido (OAuth persistido ou fallback)",
                "credentials": self._public_credentials_view(resolved),
            }

        me_response = self._request(
            method="GET",
            url=self._graph_url("me"),
            params={
                "fields": "id,name",
                "access_token": token,
            },
        )
        if me_response.get("status") != "ok":
            return {
                "status": "fail",
                "where": "GET /me",
                "message": "Meta Graph rejeitou o token na prova de saida",
                "credentials": self._public_credentials_view(resolved),
                "meta_response": me_response,
            }

        phone_response: dict[str, Any] | None = None
        if phone_number_id:
            phone_response = self._request(
                method="GET",
                url=self._graph_url(phone_number_id),
                params={
                    "fields": "id,display_phone_number,verified_name,quality_rating",
                    "access_token": token,
                },
            )

        phone_status = "skipped_no_phone_id"
        if phone_response is not None:
            phone_status = "ok" if phone_response.get("status") == "ok" else "fail"

        return {
            "status": "ok" if phone_status in {"ok", "skipped_no_phone_id"} else "degraded",
            "where": "Meta Graph API",
            "message": (
                "Conexao de saida com a Meta validada"
                if phone_status in {"ok", "skipped_no_phone_id"}
                else "Conexao principal validada, mas validacao de numero WhatsApp falhou"
            ),
            "credentials": self._public_credentials_view(resolved),
            "probe": {
                "me": me_response,
                "phone": phone_response,
                "phone_status": phone_status,
            },
        }

    def probe_inbound(self, *, recent_window_minutes: int = 60) -> dict[str, Any]:
        now_utc = datetime.now(timezone.utc)
        since = now_utc - timedelta(minutes=max(recent_window_minutes, 1))

        with SessionLocal() as db:
            last_received = (
                db.query(AuditLog)
                .filter(AuditLog.event_type == "meta_webhook_received")
                .order_by(AuditLog.created_at.desc())
                .first()
            )
            last_invalid = (
                db.query(AuditLog)
                .filter(AuditLog.event_type == "meta_webhook_invalid_signature")
                .order_by(AuditLog.created_at.desc())
                .first()
            )
            recent_received_count = (
                db.query(AuditLog)
                .filter(
                    AuditLog.event_type == "meta_webhook_received",
                    AuditLog.created_at >= since,
                )
                .count()
            )
            recent_invalid_count = (
                db.query(AuditLog)
                .filter(
                    AuditLog.event_type == "meta_webhook_invalid_signature",
                    AuditLog.created_at >= since,
                )
                .count()
            )

        last_received_at = last_received.created_at.isoformat() if last_received and last_received.created_at else None
        last_invalid_at = last_invalid.created_at.isoformat() if last_invalid and last_invalid.created_at else None

        if recent_received_count > 0 and recent_invalid_count == 0:
            status = "ok"
            message = "Webhook recebeu eventos Meta assinados corretamente no periodo recente"
        elif recent_received_count > 0 and recent_invalid_count > 0:
            status = "degraded"
            message = "Webhook recebeu eventos, mas houve assinaturas invalidas no mesmo periodo"
        elif recent_received_count == 0 and recent_invalid_count > 0:
            status = "fail"
            message = "Meta tentou entregar evento, mas webhook rejeitou por assinatura invalida"
        else:
            status = "warn"
            message = "Sem eventos recentes da Meta para provar a conexao de entrada"

        return {
            "status": status,
            "where": "/webhooks/meta",
            "message": message,
            "recent_window_minutes": recent_window_minutes,
            "recent_received_count": recent_received_count,
            "recent_invalid_signature_count": recent_invalid_count,
            "last_received_at": last_received_at,
            "last_invalid_signature_at": last_invalid_at,
        }

    def probe_live(self, *, recent_window_minutes: int = 60) -> dict[str, Any]:
        outbound = self.probe_outbound()
        inbound = self.probe_inbound(recent_window_minutes=recent_window_minutes)

        outbound_status = str(outbound.get("status") or "unknown")
        inbound_status = str(inbound.get("status") or "unknown")

        if outbound_status == "ok" and inbound_status == "ok":
            overall = "ok"
        elif "fail" in {outbound_status, inbound_status}:
            overall = "fail"
        else:
            overall = "degraded"

        return {
            "status": overall,
            "message": (
                "Conexao Meta validada em ida e volta"
                if overall == "ok"
                else "Conexao Meta sem prova completa de ida e volta"
            ),
            "outbound": outbound,
            "inbound": inbound,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
