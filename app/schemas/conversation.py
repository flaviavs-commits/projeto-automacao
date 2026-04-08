from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


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
