class MemoryService:
    """Placeholder for central memory and context assembly."""

    def build_context(self, conversation_id: str | None = None) -> dict:
        return {
            "status": "ready",
            "conversation_id": conversation_id,
            "memory_items": [],
        }
