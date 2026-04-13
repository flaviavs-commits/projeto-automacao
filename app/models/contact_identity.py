from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin, UUIDPrimaryKeyMixin, json_column


class ContactIdentity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contact_identities"
    __table_args__ = (
        UniqueConstraint("platform", "platform_user_id", name="uq_contact_identities_platform_platform_user_id"),
    )

    contact_id: Mapped[UUID] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    platform_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    normalized_value: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metadata_json: Mapped[dict] = json_column()

    contact = relationship("Contact", back_populates="identities")
