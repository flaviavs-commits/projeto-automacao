from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UUIDPrimaryKeyMixin, json_column


class Message(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "messages"

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    message_type: Mapped[str] = mapped_column(String(50), nullable=False)
    external_message_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcription: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_payload: Mapped[dict] = json_column()
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    conversation = relationship("Conversation", back_populates="messages")
