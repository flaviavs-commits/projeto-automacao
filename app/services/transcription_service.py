class TranscriptionService:
    """Prepares inbound audio items for future transcription backends."""

    def transcribe(self, media_url: str | None) -> dict:
        if not media_url:
            return {"status": "ignored", "reason": "missing_media_url"}

        return {
            "status": "queued",
            "media_url": media_url,
            "provider": None,
        }
