from pydantic import BaseModel, ConfigDict, Field


class MetaWebhookChangeValue(BaseModel):
    model_config = ConfigDict(extra="allow")


class MetaWebhookChange(BaseModel):
    model_config = ConfigDict(extra="allow")

    field: str | None = None
    value: MetaWebhookChangeValue | dict = Field(default_factory=dict)


class MetaWebhookEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    time: int | None = None
    changes: list[MetaWebhookChange] = Field(default_factory=list)
    messaging: list[dict] = Field(default_factory=list)


class MetaWebhookEnvelope(BaseModel):
    model_config = ConfigDict(extra="allow")

    object: str = "unknown"
    entry: list[MetaWebhookEntry] = Field(default_factory=list)
