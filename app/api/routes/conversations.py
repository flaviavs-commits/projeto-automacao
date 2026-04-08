from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.conversation import Conversation
from app.schemas.conversation import ConversationRead


router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationRead])
def list_conversations(db: Session = Depends(get_db)) -> list[Conversation]:
    return (
        db.query(Conversation)
        .order_by(Conversation.last_message_at.desc(), Conversation.created_at.desc())
        .limit(100)
        .all()
    )
