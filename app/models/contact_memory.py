from uuid import UUID

from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ContactMemory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contact_memories"
    __table_args__ = (
        UniqueConstraint("contact_id", "memory_key", name="uq_contact_memories_contact_id_memory_key"),
    )

    contact_id: Mapped[UUID] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    memory_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    memory_value: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active", index=True)
    importance: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    contact = relationship("Contact", back_populates="memories")
