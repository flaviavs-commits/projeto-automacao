from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.conversation import Conversation
from app.models.message import Message
from app.schemas.message import MessageCreate, MessageRead, MessageUpdate


router = APIRouter(prefix="/messages", tags=["messages"])


@router.get("", response_model=list[MessageRead])
def list_messages(db: Session = Depends(get_db)) -> list[Message]:
    return db.query(Message).order_by(Message.created_at.desc()).limit(100).all()


@router.get("/{message_id}", response_model=MessageRead)
def get_message(message_id: UUID, db: Session = Depends(get_db)) -> Message:
    message = db.get(Message, message_id)
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    return message


@router.post("", response_model=MessageRead, status_code=status.HTTP_201_CREATED)
def create_message(payload: MessageCreate, db: Session = Depends(get_db)) -> Message:
    conversation = db.get(Conversation, payload.conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    message = Message(
        conversation_id=payload.conversation_id,
        platform=payload.platform,
        direction=payload.direction,
        message_type=payload.message_type,
        external_message_id=payload.external_message_id,
        text_content=payload.text_content,
        transcription=payload.transcription,
        media_url=payload.media_url,
        raw_payload=payload.raw_payload,
        ai_generated=payload.ai_generated,
    )
    db.add(message)
    conversation.last_message_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(message)
    return message


@router.patch("/{message_id}", response_model=MessageRead)
def update_message(message_id: UUID, payload: MessageUpdate, db: Session = Depends(get_db)) -> Message:
    message = db.get(Message, message_id)
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided for update",
        )

    for field, value in updates.items():
        setattr(message, field, value)

    db.commit()
    db.refresh(message)
    return message
