from sqlalchemy import text

from fastapi import APIRouter
import redis

from app.core.config import settings
from app.core.database import SessionLocal, get_database_runtime_state
from app.workers.celery_app import get_queue_runtime_state


router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict:
    database_status = "unknown"
    redis_status = "unknown"
    database_runtime = get_database_runtime_state()
    queue_runtime = get_queue_runtime_state()

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
        "database": database_status,
        "database_mode": database_runtime.get("mode"),
        "database_fallback_reason": database_runtime.get("fallback_reason"),
        "redis": redis_status,
        "redis_mode": queue_runtime.get("mode"),
        "redis_fallback_reason": queue_runtime.get("fallback_reason"),
    }
