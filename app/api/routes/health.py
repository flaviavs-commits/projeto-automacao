from sqlalchemy import text

from fastapi import APIRouter
import redis

from app.core.config import settings
from app.core.database import SessionLocal, get_database_runtime_state
from app.services.platform_account_service import PlatformAccountService
from app.workers.celery_app import get_queue_runtime_state


router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict:
    database_status = "unknown"
    redis_status = "unknown"
    database_runtime = get_database_runtime_state()
    queue_runtime = get_queue_runtime_state()
    cached_meta_snapshot = PlatformAccountService().get_latest_meta_snapshot()
    cached_meta_token_ready = bool(cached_meta_snapshot.get("token_usable"))
    cached_meta_token_present = bool(cached_meta_snapshot.get("token_present"))
    cached_meta_token_expired = bool(cached_meta_snapshot.get("token_expired"))
    cached_instagram_account_ready = bool(cached_meta_snapshot.get("instagram_account_ready"))
    cached_whatsapp_phone_number_ready = bool(cached_meta_snapshot.get("whatsapp_phone_number_ready"))
    effective_meta_runtime_enabled = settings.meta_enabled and (
        settings.meta_ready or cached_meta_token_ready
    )
    effective_instagram_publish_ready = effective_meta_runtime_enabled and (
        bool(settings.instagram_business_account_id.strip()) or cached_instagram_account_ready
    )

    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        database_status = "ok"
    except Exception as exc:
        database_status = f"error:{exc.__class__.__name__}"

    queue_mode = str(queue_runtime.get("mode") or "")
    if queue_mode == "fallback_memory":
        redis_status = "fallback"
    elif queue_mode == "redis":
        redis_url = str(queue_runtime.get("broker_url") or "")
        try:
            client = redis.Redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
            pong = client.ping()
            redis_status = "ok" if pong else "error:NoPingResponse"
        except Exception as exc:
            redis_status = f"error:{exc.__class__.__name__}"
    else:
        redis_status = "error:QueueUnavailable"

    overall_status = "ok" if (database_status == "ok" and redis_status in {"ok", "fallback"}) else "degraded"

    return {
        "status": overall_status,
        "app": settings.app_name,
        "environment": settings.app_env,
        "integrations": {
            "meta_enabled": settings.meta_enabled,
            "meta_ready": settings.meta_ready,
            "meta_cached_token_ready": cached_meta_token_ready,
            "meta_cached_token_present": cached_meta_token_present,
            "meta_cached_token_expired": cached_meta_token_expired,
            "meta_cached_token_expires_at": cached_meta_snapshot.get("token_expires_at"),
            "meta_runtime_enabled": effective_meta_runtime_enabled,
            "meta_oauth_ready": settings.meta_oauth_ready,
            "instagram_publish_ready": effective_instagram_publish_ready,
            "instagram_cached_account_ready": cached_instagram_account_ready,
            "whatsapp_phone_number_id_configured": bool(settings.meta_whatsapp_phone_number_id.strip()),
            "whatsapp_cached_phone_number_ready": cached_whatsapp_phone_number_ready,
            "whatsapp_dispatch_ready": (
                effective_meta_runtime_enabled
                and (
                    bool(settings.meta_whatsapp_phone_number_id.strip())
                    or cached_whatsapp_phone_number_ready
                )
            ),
            "tiktok_enabled": settings.tiktok_enabled,
            "tiktok_ready": settings.tiktok_ready,
            "tiktok_runtime_enabled": settings.tiktok_runtime_enabled,
        },
        "database": database_status,
        "database_mode": database_runtime.get("mode"),
        "database_fallback_reason": database_runtime.get("fallback_reason"),
        "redis": redis_status,
        "redis_mode": queue_runtime.get("mode"),
        "redis_fallback_reason": queue_runtime.get("fallback_reason"),
    }
