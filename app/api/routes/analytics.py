from fastapi import APIRouter

from app.services.analytics_service import AnalyticsService


router = APIRouter(prefix="/analytics", tags=["analytics"])
analytics_service = AnalyticsService()


@router.get("")
def get_analytics() -> dict:
    return analytics_service.get_overview()
