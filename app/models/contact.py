from uuid import uuid4

from sqlalchemy import String
from sqlalchemy.orm import Mapped, relationship
from sqlalchemy.orm import mapped_column

from app.core.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


def _generate_customer_id() -> str:
    return f"CUST-{uuid4().hex[:12].upper()}"


class Contact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contacts"

    customer_id: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        unique=True,
        index=True,
        default=_generate_customer_id,
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    instagram_user_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    youtube_channel_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    tiktok_user_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    conversations = relationship("Conversation", back_populates="contact")
    identities = relationship("ContactIdentity", back_populates="contact")
    memories = relationship("ContactMemory", back_populates="contact")
