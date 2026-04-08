from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ContactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str | None
    phone: str | None
    instagram_user_id: str | None
    youtube_channel_id: str | None
    tiktok_user_id: str | None
    email: str | None
    created_at: datetime
    updated_at: datetime
