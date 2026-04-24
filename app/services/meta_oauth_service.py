from urllib.parse import urlencode

from app.core.config import settings
from app.services.base import BaseExternalService


class MetaOAuthService(BaseExternalService):
    """Handles OAuth interactions with the Meta/Facebook Graph API."""

    service_name = "meta_oauth"

    def _graph_url(self, path: str) -> str:
        base = settings.meta_graph_base_url.rstrip("/")
        normalized_path = path.lstrip("/")
        return f"{base}/{settings.meta_api_version}/{normalized_path}"

    def _auth_dialog_url(self) -> str:
        base = settings.meta_auth_base_url.rstrip("/")
        return f"{base}/{settings.meta_api_version}/dialog/oauth"

    def build_authorization_url(
        self,
        *,
        redirect_uri: str,
        state: str,
        scopes: str,
    ) -> str:
        params = {
            "client_id": settings.effective_meta_app_id.strip(),
            "redirect_uri": redirect_uri,
            "scope": scopes,
            "state": state,
            "response_type": "code",
        }
        return f"{self._auth_dialog_url()}?{urlencode(params)}"

    def exchange_code_for_short_lived_token(
        self,
        *,
        code: str,
        redirect_uri: str,
    ) -> dict:
        return self._request(
            method="GET",
            url=self._graph_url("oauth/access_token"),
            params={
                "client_id": settings.effective_meta_app_id.strip(),
                "client_secret": settings.effective_meta_app_secret.strip(),
                "redirect_uri": redirect_uri,
                "code": code,
            },
        )

    def exchange_for_long_lived_token(self, *, short_lived_token: str) -> dict:
        return self._request(
            method="GET",
            url=self._graph_url("oauth/access_token"),
            params={
                "grant_type": "fb_exchange_token",
                "client_id": settings.effective_meta_app_id.strip(),
                "client_secret": settings.effective_meta_app_secret.strip(),
                "fb_exchange_token": short_lived_token,
            },
        )

    def fetch_profile(self, *, access_token: str) -> dict:
        return self._request(
            method="GET",
            url=self._graph_url("me"),
            params={
                "fields": "id,name",
                "access_token": access_token,
            },
        )

    def fetch_pages(self, *, access_token: str) -> dict:
        return self._request(
            method="GET",
            url=self._graph_url("me/accounts"),
            params={
                "fields": (
                    "id,name,"
                    "instagram_business_account{id,username},"
                    "whatsapp_business_account{id,name,phone_numbers{id,display_phone_number,verified_name}}"
                ),
                "access_token": access_token,
            },
        )

    def subscribe_instagram_app(
        self,
        *,
        instagram_business_account_id: str,
        access_token: str,
    ) -> dict:
        target_id = str(instagram_business_account_id or "").strip()
        if not target_id:
            return self.invalid_payload("subscribe_instagram_app", "instagram_business_account_id is required")
        return self._request(
            method="POST",
            url=self._graph_url(f"{target_id}/subscribed_apps"),
            form_payload={
                "subscribed_fields": "messages,messaging_postbacks,message_reactions,messaging_seen",
                "access_token": access_token,
            },
        )
