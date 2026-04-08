class RoutingService:
    """Determines the next handler for inbound events."""

    def route_intent(self, payload: dict) -> dict:
        return {
            "status": "ready",
            "route": "unclassified",
            "payload_received": bool(payload),
        }
