class AnalyticsService:
    """Provides safe aggregate placeholders for the future dashboard."""

    def get_overview(self) -> dict:
        return {
            "status": "ready",
            "metrics": {
                "contacts": 0,
                "conversations": 0,
                "messages": 0,
                "posts": 0,
                "pending_jobs": 0,
            },
            "notes": "Dashboard analytics endpoints are prepared for database-backed aggregation.",
        }
