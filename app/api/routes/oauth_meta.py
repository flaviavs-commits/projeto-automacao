from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.security import (
    encrypt_secret,
    is_state_payload_fresh,
    sign_state_payload,
    verify_state_payload,
)
from app.models.audit_log import AuditLog
from app.models.platform_account import PlatformAccount
from app.services.meta_oauth_service import MetaOAuthService


router = APIRouter(prefix="/oauth", tags=["oauth"])
logger = get_logger(__name__)


def _normalize_scopes(scopes: str | None) -> str:
    raw = str(scopes or settings.meta_oauth_scopes or "").replace(",", " ")
    items: list[str] = []
    for part in raw.split():
        scope = part.strip()
        if scope and scope not in items:
            items.append(scope)
    return ",".join(items)


def _resolve_redirect_uri(
    *,
    request: Request,
    explicit_redirect_uri: str | None,
    callback_route_name: str,
) -> str:
    explicit = str(explicit_redirect_uri or "").strip()
    if explicit:
        return explicit
    configured = str(settings.meta_oauth_redirect_uri or "").strip()
    if configured:
        return configured
    return str(request.url_for(callback_route_name))


def _require_meta_oauth_configuration() -> None:
    if not settings.meta_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Meta integration is disabled (META_ENABLED=false)",
        )
    if not settings.meta_oauth_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Meta OAuth is not configured "
                "(META_APP_ID/META_APP_SECRET or INSTAGRAM_APP_ID/INSTAGRAM_APP_SECRET)"
            ),
        )
    if not settings.effective_oauth_state_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth state secret is missing (OAUTH_STATE_SECRET or META_APP_SECRET)",
        )
    if not settings.effective_token_encryption_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Token encryption secret is missing (TOKEN_ENCRYPTION_SECRET or META_APP_SECRET)",
        )


def _normalize_instagram_username(value: str | None) -> str:
    cleaned = str(value or "").strip().lower()
    if cleaned.startswith("@"):
        cleaned = cleaned[1:]
    return cleaned


def _extract_meta_assets_from_pages_payload(
    pages_payload: dict,
    *,
    preferred_instagram_username: str | None = None,
    preferred_instagram_business_account_id: str | None = None,
) -> tuple[str | None, str | None, str | None, str | None, list[dict[str, str | None]]]:
    data = pages_payload.get("data")
    if not isinstance(data, list):
        return None, None, None, None, []

    fallback_whatsapp_business_account_id = None
    fallback_whatsapp_phone_number_id = None
    available_instagram_accounts: list[dict[str, str | None]] = []
    candidates: list[dict[str, str | None]] = []
    for page in data:
        if not isinstance(page, dict):
            continue

        page_id = str(page.get("id") or "").strip() or None
        page_name = str(page.get("name") or "").strip() or None
        ig = page.get("instagram_business_account")
        if isinstance(ig, dict):
            ig_id = str(ig.get("id") or "").strip() or None
            ig_username = str(ig.get("username") or "").strip() or None
        else:
            ig_id = None
            ig_username = None

        waba = page.get("whatsapp_business_account")
        page_whatsapp_business_account_id = None
        page_whatsapp_phone_number_id = None
        if isinstance(waba, dict):
            page_whatsapp_business_account_id = str(waba.get("id") or "").strip() or None
            phone_numbers = waba.get("phone_numbers")
            if isinstance(phone_numbers, list) and phone_numbers:
                for item in phone_numbers:
                    if not isinstance(item, dict):
                        continue
                    candidate = str(item.get("id") or "").strip()
                    if candidate:
                        page_whatsapp_phone_number_id = candidate
                        break
            if page_whatsapp_phone_number_id is None:
                candidate_direct = str(waba.get("phone_number_id") or "").strip()
                if candidate_direct:
                    page_whatsapp_phone_number_id = candidate_direct

        if fallback_whatsapp_business_account_id is None and page_whatsapp_business_account_id is not None:
            fallback_whatsapp_business_account_id = page_whatsapp_business_account_id
        if fallback_whatsapp_phone_number_id is None and page_whatsapp_phone_number_id is not None:
            fallback_whatsapp_phone_number_id = page_whatsapp_phone_number_id

        if ig_id or ig_username:
            row = {
                "page_id": page_id,
                "page_name": page_name,
                "instagram_business_account_id": ig_id,
                "instagram_username": ig_username,
                "whatsapp_business_account_id": page_whatsapp_business_account_id,
                "whatsapp_phone_number_id": page_whatsapp_phone_number_id,
            }
            available_instagram_accounts.append(row)
            candidates.append(row)

    selected: dict[str, str | None] | None = None
    preferred_ig_id = str(preferred_instagram_business_account_id or "").strip()
    preferred_ig_username = _normalize_instagram_username(preferred_instagram_username)
    if preferred_ig_id:
        selected = next(
            (item for item in candidates if str(item.get("instagram_business_account_id") or "").strip() == preferred_ig_id),
            None,
        )
    if selected is None and preferred_ig_username:
        selected = next(
            (
                item
                for item in candidates
                if _normalize_instagram_username(item.get("instagram_username")) == preferred_ig_username
            ),
            None,
        )
    if selected is None and candidates:
        selected = candidates[0]

    if selected is None:
        return (
            None,
            None,
            fallback_whatsapp_business_account_id,
            fallback_whatsapp_phone_number_id,
            available_instagram_accounts,
        )

    whatsapp_business_account_id = selected.get("whatsapp_business_account_id") or fallback_whatsapp_business_account_id
    whatsapp_phone_number_id = selected.get("whatsapp_phone_number_id") or fallback_whatsapp_phone_number_id
    return (
        selected.get("instagram_business_account_id"),
        selected.get("instagram_username"),
        whatsapp_business_account_id,
        whatsapp_phone_number_id,
        available_instagram_accounts,
    )


def _build_state_payload(
    *,
    redirect_uri: str,
    scopes: str,
    preferred_instagram_username: str | None,
    preferred_instagram_business_account_id: str | None,
) -> dict:
    payload = {
        "provider": "meta",
        "redirect_uri": redirect_uri,
        "scopes": scopes,
        "nonce": uuid4().hex,
        "iat": int(datetime.now(timezone.utc).timestamp()),
    }
    normalized_username = _normalize_instagram_username(preferred_instagram_username)
    preferred_ig_id = str(preferred_instagram_business_account_id or "").strip()
    if normalized_username:
        payload["preferred_instagram_username"] = normalized_username
    if preferred_ig_id:
        payload["preferred_instagram_business_account_id"] = preferred_ig_id
    return payload


def _build_start_response(
    *,
    request: Request,
    callback_route_name: str,
    redirect_uri: str | None,
    scopes: str | None,
    preferred_instagram_username: str | None,
    preferred_instagram_business_account_id: str | None,
    return_url: bool,
) -> dict | RedirectResponse:
    _require_meta_oauth_configuration()

    resolved_redirect_uri = _resolve_redirect_uri(
        request=request,
        explicit_redirect_uri=redirect_uri,
        callback_route_name=callback_route_name,
    )
    resolved_scopes = _normalize_scopes(scopes)
    if not resolved_scopes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth scopes are empty (META_OAUTH_SCOPES)",
        )

    state_payload = _build_state_payload(
        redirect_uri=resolved_redirect_uri,
        scopes=resolved_scopes,
        preferred_instagram_username=preferred_instagram_username,
        preferred_instagram_business_account_id=preferred_instagram_business_account_id,
    )
    signed_state = sign_state_payload(
        state_payload,
        secret=settings.effective_oauth_state_secret,
    )

    oauth_url = MetaOAuthService().build_authorization_url(
        redirect_uri=resolved_redirect_uri,
        state=signed_state,
        scopes=resolved_scopes,
    )

    if return_url:
        return {
            "status": "ok",
            "provider": "meta",
            "authorization_url": oauth_url,
            "redirect_uri": resolved_redirect_uri,
            "scopes": resolved_scopes.split(","),
        }
    return RedirectResponse(url=oauth_url, status_code=status.HTTP_302_FOUND)


@router.get("/meta/start", response_model=None)
def start_meta_oauth(
    request: Request,
    redirect_uri: str | None = Query(default=None),
    scopes: str | None = Query(default=None),
    preferred_instagram_username: str | None = Query(default=None),
    preferred_instagram_business_account_id: str | None = Query(default=None),
    return_url: bool = Query(default=False),
) -> dict | RedirectResponse:
    return _build_start_response(
        request=request,
        callback_route_name="oauth_meta_callback",
        redirect_uri=redirect_uri,
        scopes=scopes,
        preferred_instagram_username=preferred_instagram_username,
        preferred_instagram_business_account_id=preferred_instagram_business_account_id,
        return_url=return_url,
    )


@router.get("/facebook/start", response_model=None)
def start_facebook_oauth(
    request: Request,
    redirect_uri: str | None = Query(default=None),
    scopes: str | None = Query(default=None),
    preferred_instagram_username: str | None = Query(default=None),
    preferred_instagram_business_account_id: str | None = Query(default=None),
    return_url: bool = Query(default=False),
) -> dict | RedirectResponse:
    return _build_start_response(
        request=request,
        callback_route_name="oauth_facebook_callback",
        redirect_uri=redirect_uri,
        scopes=scopes,
        preferred_instagram_username=preferred_instagram_username,
        preferred_instagram_business_account_id=preferred_instagram_business_account_id,
        return_url=return_url,
    )


@router.get("/meta/callback", name="oauth_meta_callback")
@router.get("/facebook/callback", name="oauth_facebook_callback")
def oauth_meta_callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    _require_meta_oauth_configuration()

    if error:
        detail = str(error_description or error).strip()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Meta OAuth returned an error: {detail}",
        )
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing OAuth code",
        )
    if not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing OAuth state",
        )

    state_payload = verify_state_payload(
        state,
        secret=settings.effective_oauth_state_secret,
    )
    if state_payload is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth state signature",
        )
    if not is_state_payload_fresh(
        state_payload,
        max_age_seconds=settings.oauth_state_ttl_seconds,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state expired",
        )

    redirect_uri = str(state_payload.get("redirect_uri") or "").strip()
    if not redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth state payload: redirect_uri missing",
        )
    requested_scopes = _normalize_scopes(str(state_payload.get("scopes") or ""))

    oauth_service = MetaOAuthService()
    short_token_result = oauth_service.exchange_code_for_short_lived_token(
        code=code,
        redirect_uri=redirect_uri,
    )
    if short_token_result.get("status") != "ok":
        logger.warning(
            "meta_oauth_token_exchange_failed",
            extra={
                "path": str(request.url.path),
                "status_code": short_token_result.get("status_code"),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": "Meta token exchange failed",
                "result": short_token_result,
            },
        )

    short_token_body = short_token_result.get("body")
    if not isinstance(short_token_body, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Meta token exchange returned an invalid body",
        )

    short_lived_token = str(short_token_body.get("access_token") or "").strip()
    if not short_lived_token:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Meta token exchange did not return access_token",
        )

    active_access_token = short_lived_token
    token_source = "short_lived"
    expires_in = short_token_body.get("expires_in")
    long_lived_result = oauth_service.exchange_for_long_lived_token(
        short_lived_token=short_lived_token,
    )
    if long_lived_result.get("status") == "ok":
        long_lived_body = long_lived_result.get("body")
        if isinstance(long_lived_body, dict):
            long_lived_token = str(long_lived_body.get("access_token") or "").strip()
            if long_lived_token:
                active_access_token = long_lived_token
                token_source = "long_lived"
            if long_lived_body.get("expires_in") is not None:
                expires_in = long_lived_body.get("expires_in")

    profile_result = oauth_service.fetch_profile(access_token=active_access_token)
    if profile_result.get("status") != "ok":
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": "Meta profile lookup failed",
                "result": profile_result,
            },
        )

    profile_body = profile_result.get("body")
    if not isinstance(profile_body, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Meta profile response is invalid",
        )

    external_account_id = str(profile_body.get("id") or "").strip()
    if not external_account_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Meta profile response did not include account id",
        )
    profile_name = str(profile_body.get("name") or "").strip() or None

    pages_result = oauth_service.fetch_pages(access_token=active_access_token)
    pages_body: dict = {}
    if pages_result.get("status") == "ok" and isinstance(pages_result.get("body"), dict):
        pages_body = pages_result.get("body") or {}

    preferred_instagram_username = str(state_payload.get("preferred_instagram_username") or "").strip() or None
    preferred_instagram_business_account_id = (
        str(state_payload.get("preferred_instagram_business_account_id") or "").strip() or None
    )
    (
        instagram_business_account_id,
        instagram_username,
        whatsapp_business_account_id,
        whatsapp_phone_number_id,
        available_instagram_accounts,
    ) = _extract_meta_assets_from_pages_payload(
        pages_body,
        preferred_instagram_username=preferred_instagram_username,
        preferred_instagram_business_account_id=preferred_instagram_business_account_id,
    )
    instagram_subscription_result: dict | None = None
    if instagram_business_account_id:
        subscription_try = oauth_service.subscribe_instagram_app(
            instagram_business_account_id=instagram_business_account_id,
            access_token=active_access_token,
        )
        if subscription_try.get("status") == "ok":
            instagram_subscription_result = {"status": "ok", "result": subscription_try.get("body")}
        else:
            instagram_subscription_result = {
                "status": "failed",
                "status_code": subscription_try.get("status_code"),
                "detail": subscription_try.get("detail"),
            }
    encrypted_access_token = encrypt_secret(
        active_access_token,
        secret=settings.effective_token_encryption_secret,
    )

    token_expires_at = None
    if expires_in is not None:
        try:
            expires_in_int = int(expires_in)
            if expires_in_int > 0:
                token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in_int)
        except Exception:  # noqa: BLE001
            token_expires_at = None

    account = (
        db.query(PlatformAccount)
        .filter(
            PlatformAccount.platform == "meta",
            PlatformAccount.external_account_id == external_account_id,
        )
        .first()
    )
    if account is None:
        account = PlatformAccount(
            platform="meta",
            external_account_id=external_account_id,
        )
        db.add(account)
        db.flush()

    account.access_token_encrypted = encrypted_access_token
    account.token_expires_at = token_expires_at
    existing_metadata = account.metadata_json if isinstance(account.metadata_json, dict) else {}
    account.metadata_json = {
        **existing_metadata,
        "provider": "facebook",
        "profile_name": profile_name,
        "oauth_redirect_uri": redirect_uri,
        "oauth_token_source": token_source,
        "oauth_connected_at": datetime.now(timezone.utc).isoformat(),
        "oauth_scopes": requested_scopes.split(",") if requested_scopes else [],
        "instagram_business_account_id": instagram_business_account_id,
        "instagram_username": instagram_username,
        "whatsapp_business_account_id": whatsapp_business_account_id,
        "whatsapp_phone_number_id": whatsapp_phone_number_id,
        "pages_result_status": pages_result.get("status"),
        "instagram_subscription": instagram_subscription_result,
    }

    db.add(
        AuditLog(
            entity_type="platform_account",
            entity_id=account.id,
            event_type="meta_oauth_connected",
            details={
                "platform_account_id": str(account.id),
                "platform": account.platform,
                "external_account_id": external_account_id,
                "profile_name": profile_name,
                "token_source": token_source,
                "token_expires_at": (
                    token_expires_at.isoformat() if token_expires_at is not None else None
                ),
                "instagram_business_account_id": instagram_business_account_id,
                "instagram_username": instagram_username,
                "whatsapp_business_account_id": whatsapp_business_account_id,
                "whatsapp_phone_number_id": whatsapp_phone_number_id,
                "instagram_subscription": instagram_subscription_result,
            },
        )
    )
    db.commit()
    db.refresh(account)

    return {
        "status": "connected",
        "provider": "meta",
        "platform_account_id": str(account.id),
        "external_account_id": external_account_id,
        "profile_name": profile_name,
        "token_source": token_source,
        "token_expires_at": token_expires_at.isoformat() if token_expires_at is not None else None,
        "instagram_business_account_id": instagram_business_account_id,
        "instagram_username": instagram_username,
        "available_instagram_accounts": available_instagram_accounts,
        "whatsapp_business_account_id": whatsapp_business_account_id,
        "whatsapp_phone_number_id": whatsapp_phone_number_id,
        "instagram_subscription": instagram_subscription_result,
        "redirect_uri": redirect_uri,
        "next_steps": [
            "Token salvo em platform_accounts e pronto para fallback automatico dos servicos Meta",
            "Definir INSTAGRAM_BUSINESS_ACCOUNT_ID com o valor retornado acima",
        ],
    }
