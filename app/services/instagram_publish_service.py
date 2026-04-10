from app.core.config import settings
from app.services.base import BaseExternalService
from app.services.platform_account_service import PlatformAccountService


class InstagramPublishService(BaseExternalService):
    """Encapsulates Instagram publishing operations."""

    service_name = "instagram_publish"

    def _graph_url(self, object_id: str, edge: str) -> str:
        base = settings.meta_graph_base_url.rstrip("/")
        return f"{base}/{settings.meta_api_version}/{object_id}/{edge}"

    def publish_post(self, payload: dict) -> dict:
        if not payload:
            return {"status": "ignored", "reason": "empty_payload"}
        if not settings.meta_enabled:
            return self.integration_disabled("publish_post", "meta_disabled")

        persisted_credentials = PlatformAccountService().get_latest_meta_credentials()
        ig_user_id = str(
            payload.get("ig_user_id")
            or settings.instagram_business_account_id
            or persisted_credentials.get("instagram_business_account_id")
        ).strip()
        access_token = str(
            payload.get("access_token")
            or settings.meta_access_token
            or persisted_credentials.get("access_token")
        ).strip()
        image_url = str(payload.get("image_url") or payload.get("media_url") or "").strip()
        caption = str(payload.get("caption") or "").strip()

        if not ig_user_id or not access_token:
            return self.missing_credentials(
                "publish_post",
                [
                    "INSTAGRAM_BUSINESS_ACCOUNT_ID (or OAuth metadata)",
                    "META_ACCESS_TOKEN (or OAuth stored token)",
                ],
            )
        if not image_url:
            return self.invalid_payload("publish_post", "field 'image_url' (or 'media_url') is required")

        create_resp = self._request(
            method="POST",
            url=self._graph_url(ig_user_id, "media"),
            form_payload={
                "image_url": image_url,
                "caption": caption,
                "access_token": access_token,
            },
        )
        if create_resp.get("status") != "ok":
            return create_resp

        create_body = create_resp.get("body")
        creation_id = None
        if isinstance(create_body, dict):
            creation_id = create_body.get("id")
        if not creation_id:
            return self.request_failed(
                "publish_post",
                "Instagram did not return media creation id",
            )

        publish_resp = self._request(
            method="POST",
            url=self._graph_url(ig_user_id, "media_publish"),
            form_payload={
                "creation_id": creation_id,
                "access_token": access_token,
            },
        )
        if publish_resp.get("status") != "ok":
            return publish_resp

        publish_body = publish_resp.get("body")
        published_post_id = None
        if isinstance(publish_body, dict):
            published_post_id = publish_body.get("id")

        return {
            "status": "published",
            "service": self.service_name,
            "action": "publish_post",
            "creation_id": creation_id,
            "published_post_id": published_post_id,
            "raw": publish_body,
        }
