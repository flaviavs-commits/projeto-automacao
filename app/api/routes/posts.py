from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.post import Post
from app.schemas.post import PostCreate, PostRead, PostUpdate
from app.services.platform_account_service import PlatformAccountService


router = APIRouter(prefix="/posts", tags=["posts"])
META_PLATFORMS = {"meta", "facebook", "instagram", "whatsapp"}
TIKTOK_PLATFORMS = {"tiktok"}
_BLOCKABLE_STATUSES = {"", "draft", "queued", "pending", "scheduled", "processing", "retry"}


def _normalize_platform(value: str) -> str:
    return str(value or "").strip().lower()


def _normalize_payload(value: dict | None) -> dict:
    return value if isinstance(value, dict) else {}


def _with_block_reason(platform_payload: dict, *, reason: str, platform: str) -> dict:
    return {
        **platform_payload,
        "_integration_block": {
            "reason": reason,
            "platform": platform,
            "at": datetime.now(timezone.utc).isoformat(),
        },
    }


def _meta_runtime_enabled_effective() -> bool:
    if not settings.meta_enabled:
        return False
    if settings.meta_runtime_enabled:
        return True
    cached = PlatformAccountService().get_latest_meta_credentials()
    return bool(str(cached.get("access_token") or "").strip())


def _apply_platform_fallback(platform: str, status_value: str, platform_payload: dict) -> tuple[str, dict]:
    normalized_platform = _normalize_platform(platform)
    normalized_status = str(status_value or "").strip().lower()

    if normalized_platform in META_PLATFORMS and not _meta_runtime_enabled_effective():
        if normalized_status in _BLOCKABLE_STATUSES:
            return (
                "pending_meta_review",
                _with_block_reason(
                    platform_payload,
                    reason="meta_unavailable",
                    platform=normalized_platform,
                ),
            )

    if normalized_platform in TIKTOK_PLATFORMS and not settings.tiktok_runtime_enabled:
        if normalized_status in _BLOCKABLE_STATUSES:
            return (
                "pending_tiktok_setup",
                _with_block_reason(
                    platform_payload,
                    reason="tiktok_unavailable",
                    platform=normalized_platform,
                ),
            )

    return status_value, platform_payload


@router.get("", response_model=list[PostRead])
def list_posts(db: Session = Depends(get_db)) -> list[Post]:
    return db.query(Post).order_by(Post.created_at.desc()).limit(100).all()


@router.get("/{post_id}", response_model=PostRead)
def get_post(post_id: UUID, db: Session = Depends(get_db)) -> Post:
    post = db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return post


@router.post("", response_model=PostRead, status_code=status.HTTP_201_CREATED)
def create_post(payload: PostCreate, db: Session = Depends(get_db)) -> Post:
    platform = _normalize_platform(payload.platform)
    platform_payload = _normalize_payload(payload.platform_payload)
    status_value, platform_payload = _apply_platform_fallback(
        platform=platform,
        status_value=payload.status,
        platform_payload=platform_payload,
    )

    post = Post(
        platform=platform,
        status=status_value,
        title=payload.title,
        caption=payload.caption,
        media_url=payload.media_url,
        scheduled_at=payload.scheduled_at,
        published_at=payload.published_at,
        external_post_id=payload.external_post_id,
        platform_payload=platform_payload,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


@router.patch("/{post_id}", response_model=PostRead)
def update_post(post_id: UUID, payload: PostUpdate, db: Session = Depends(get_db)) -> Post:
    post = db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided for update",
        )

    for field, value in updates.items():
        setattr(post, field, value)

    normalized_platform = _normalize_platform(post.platform)
    current_payload = _normalize_payload(post.platform_payload)
    status_value, platform_payload = _apply_platform_fallback(
        platform=normalized_platform,
        status_value=post.status,
        platform_payload=current_payload,
    )
    post.status = status_value
    post.platform_payload = platform_payload

    db.commit()
    db.refresh(post)
    return post
