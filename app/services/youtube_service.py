from app.core.config import settings
from app.services.base import BaseExternalService


class YouTubeService(BaseExternalService):
    """Encapsulates YouTube publishing and comment sync workflows."""

    service_name = "youtube"

    def publish_video(self, payload: dict) -> dict:
        if not payload:
            return {"status": "ignored", "reason": "empty_payload"}

        upload_url = str(payload.get("upload_url") or "").strip()
        access_token = str(payload.get("access_token") or "").strip()
        body = payload.get("body")

        if not upload_url or not access_token:
            return self.missing_credentials(
                "publish_video",
                ["access_token", "upload_url"],
            )
        if body is not None and not isinstance(body, dict):
            return self.invalid_payload("publish_video", "field 'body' must be a JSON object when provided")

        response = self._request(
            method="POST",
            url=upload_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json_payload=body or {},
        )
        if response.get("status") != "ok":
            return response

        return {
            "status": "published",
            "service": self.service_name,
            "action": "publish_video",
            "raw": response.get("body"),
        }

    def sync_comments(self, channel_id: str | None = None) -> dict:
        if not channel_id:
            return {"status": "ignored", "reason": "missing_channel_id"}

        api_key = settings.youtube_api_key.strip()
        if not api_key:
            return self.missing_credentials("sync_comments", ["YOUTUBE_API_KEY"])

        url = "https://www.googleapis.com/youtube/v3/commentThreads"
        response = self._request(
            method="GET",
            url=url,
            params={
                "part": "snippet",
                "allThreadsRelatedToChannelId": channel_id,
                "maxResults": 20,
                "key": api_key,
            },
        )
        if response.get("status") != "ok":
            return response

        body = response.get("body")
        comments_count = None
        if isinstance(body, dict):
            items = body.get("items")
            if isinstance(items, list):
                comments_count = len(items)

        return {
            "status": "synced",
            "service": self.service_name,
            "action": "sync_comments",
            "channel_id": channel_id,
            "comments_count": comments_count,
            "raw": body,
        }
