from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


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
