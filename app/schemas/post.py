from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PostCreate(BaseModel):
    platform: str = Field(min_length=1, max_length=50)
    status: str = Field(default="draft", min_length=1, max_length=50)
    title: str | None = Field(default=None, max_length=255)
    caption: str | None = None
    media_url: str | None = Field(default=None, max_length=500)
    scheduled_at: datetime | None = None
    published_at: datetime | None = None
    external_post_id: str | None = Field(default=None, max_length=255)
    platform_payload: dict = Field(default_factory=dict)


class PostUpdate(BaseModel):
    status: str | None = Field(default=None, min_length=1, max_length=50)
    title: str | None = Field(default=None, max_length=255)
    caption: str | None = None
    media_url: str | None = Field(default=None, max_length=500)
    scheduled_at: datetime | None = None
    published_at: datetime | None = None
    external_post_id: str | None = Field(default=None, max_length=255)
    platform_payload: dict | None = None


class PostRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    platform: str
    status: str
    title: str | None
    caption: str | None
    media_url: str | None
    scheduled_at: datetime | None
    published_at: datetime | None
    external_post_id: str | None
    platform_payload: dict
    created_at: datetime
    updated_at: datetime
