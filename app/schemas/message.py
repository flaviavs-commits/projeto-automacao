from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MessageCreate(BaseModel):
    conversation_id: UUID
    platform: str = Field(min_length=1, max_length=50)
    direction: str = Field(min_length=1, max_length=20)
    message_type: str = Field(min_length=1, max_length=50)
    external_message_id: str | None = Field(default=None, max_length=255)
    text_content: str | None = None
    transcription: str | None = None
    media_url: str | None = Field(default=None, max_length=500)
    raw_payload: dict = Field(default_factory=dict)
    ai_generated: bool = False


class MessageUpdate(BaseModel):
    text_content: str | None = None
    transcription: str | None = None
    media_url: str | None = Field(default=None, max_length=500)
    raw_payload: dict | None = None


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    platform: str
    direction: str
    message_type: str
    external_message_id: str | None
    text_content: str | None
    transcription: str | None
    media_url: str | None
    raw_payload: dict
    ai_generated: bool
    created_at: datetime
