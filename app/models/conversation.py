from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin, UUIDPrimaryKeyMixin, json_column


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    contact_id: Mapped[UUID] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="open")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    last_inbound_message_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_inbound_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    menu_state: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    needs_human: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    human_status: Mapped[str] = mapped_column(String(30), nullable=False, default="closed", index=True)
    human_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    human_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    human_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    human_accepted_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    human_ignored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    human_ignored_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    chatbot_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    customer_collection_data: Mapped[dict] = json_column()
    customer_collection_step: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)

    contact = relationship("Contact", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation")
