from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


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
