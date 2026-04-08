from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.post import Post
from app.schemas.post import PostRead


router = APIRouter(prefix="/posts", tags=["posts"])


@router.get("", response_model=list[PostRead])
def list_posts(db: Session = Depends(get_db)) -> list[Post]:
    return db.query(Post).order_by(Post.created_at.desc()).limit(100).all()
