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
    menu_state: str | None = None
    needs_human: bool | None = None
    human_reason: str | None = None
    human_requested_at: datetime | None = None
    human_status: str | None = None
    human_accepted_at: datetime | None = None
    human_accepted_by: str | None = None
    human_ignored_at: datetime | None = None
    human_ignored_by: str | None = None
    chatbot_enabled: bool | None = None


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    contact_id: UUID
    platform: str
    status: str
    summary: str | None
    last_message_at: datetime | None
    last_inbound_message_text: str | None
    last_inbound_message_at: datetime | None
    menu_state: str | None
    needs_human: bool
    human_status: str
    human_reason: str | None
    human_requested_at: datetime | None
    human_accepted_at: datetime | None
    human_accepted_by: str | None
    human_ignored_at: datetime | None
    human_ignored_by: str | None
    chatbot_enabled: bool
    created_at: datetime
    updated_at: datetime
