from pydantic import BaseModel, ConfigDict, Field


class EvolutionWebhookMessageKey(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    remoteJid: str | None = None
    fromMe: bool | None = None


class EvolutionWebhookMessageData(BaseModel):
    model_config = ConfigDict(extra="allow")

    key: EvolutionWebhookMessageKey | dict = Field(default_factory=dict)
    pushName: str | None = None
    message: dict = Field(default_factory=dict)


class EvolutionWebhookEnvelope(BaseModel):
    model_config = ConfigDict(extra="allow")

    event: str = "unknown"
    data: dict | list[dict] | EvolutionWebhookMessageData | list[EvolutionWebhookMessageData] = Field(
        default_factory=dict
    )
