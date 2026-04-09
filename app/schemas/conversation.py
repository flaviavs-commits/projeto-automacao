from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    contact_id: UUID
    platform: str = Field(min_length=1, max_length=50)
    status: str = Field(default="open", min_length=1, max_length=50)
    summary: str | None = None
    last_message_at: datetime | None = None


class ConversationUpdate(BaseModel):
    status: str | None = Field(default=None, min_length=1, max_length=50)
    summary: str | None = None
    last_message_at: datetime | None = None


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    contact_id: UUID
    platform: str
    status: str
    summary: str | None
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime
