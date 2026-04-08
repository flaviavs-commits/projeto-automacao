from sqlalchemy import text

from fastapi import APIRouter

from app.core.config import settings
from app.core.database import SessionLocal


router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict:
    database_status = "unknown"

    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        database_status = "ok"
    except Exception as exc:
        database_status = f"error:{exc.__class__.__name__}"

    overall_status = "ok" if database_status == "ok" else "degraded"

    return {
        "status": overall_status,
        "app": settings.app_name,
        "environment": settings.app_env,
        "database": database_status,
        "redis": "configured" if settings.redis_url else "missing",
    }
