from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin, UUIDPrimaryKeyMixin, json_column


class PlatformAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "platform_accounts"

    platform: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    external_account_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    access_token_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    metadata_json: Mapped[dict] = json_column()
