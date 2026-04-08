from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.message import Message
from app.schemas.message import MessageRead


router = APIRouter(prefix="/messages", tags=["messages"])


@router.get("", response_model=list[MessageRead])
def list_messages(db: Session = Depends(get_db)) -> list[Message]:
    return db.query(Message).order_by(Message.created_at.desc()).limit(100).all()
