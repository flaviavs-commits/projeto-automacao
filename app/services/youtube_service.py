from app.services.base import BaseExternalService


class YouTubeService(BaseExternalService):
    """Encapsulates YouTube publishing and comment sync workflows."""

    service_name = "youtube"

    def publish_video(self, payload: dict) -> dict:
        if not payload:
            return {"status": "ignored", "reason": "empty_payload"}
        return self.not_configured("publish_video")

    def sync_comments(self, channel_id: str | None = None) -> dict:
        if not channel_id:
            return {"status": "ignored", "reason": "missing_channel_id"}
        return self.not_configured("sync_comments")
