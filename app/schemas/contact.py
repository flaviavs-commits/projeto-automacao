from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContactCreate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    instagram_user_id: str | None = Field(default=None, max_length=255)
    youtube_channel_id: str | None = Field(default=None, max_length=255)
    tiktok_user_id: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_identity_fields(self) -> "ContactCreate":
        if any(
            (
                self.phone,
                self.email,
                self.instagram_user_id,
                self.youtube_channel_id,
                self.tiktok_user_id,
            )
        ):
            return self
        raise ValueError(
            "at least one identity field is required: phone, email, instagram_user_id, "
            "youtube_channel_id or tiktok_user_id"
        )


class ContactUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    instagram_user_id: str | None = Field(default=None, max_length=255)
    youtube_channel_id: str | None = Field(default=None, max_length=255)
    tiktok_user_id: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)


class ContactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: str
    name: str | None
    phone: str | None
    instagram_user_id: str | None
    youtube_channel_id: str | None
    tiktok_user_id: str | None
    email: str | None
    created_at: datetime
    updated_at: datetime
