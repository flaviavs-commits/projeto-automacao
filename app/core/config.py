from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="bot-multiredes", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_port: int = Field(
        default=8000,
        validation_alias=AliasChoices("APP_PORT", "PORT"),
    )
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/bot_multiredes",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    meta_enabled: bool = Field(default=True, alias="META_ENABLED")
    meta_verify_token: str = Field(default="change-me", alias="META_VERIFY_TOKEN")
    meta_access_token: str = Field(default="", alias="META_ACCESS_TOKEN")
    meta_graph_base_url: str = Field(default="https://graph.facebook.com", alias="META_GRAPH_BASE_URL")
    meta_auth_base_url: str = Field(default="https://www.facebook.com", alias="META_AUTH_BASE_URL")
    meta_api_version: str = Field(default="v23.0", alias="META_API_VERSION")
    meta_whatsapp_phone_number_id: str = Field(default="", alias="META_WHATSAPP_PHONE_NUMBER_ID")
    whatsapp_provider: str = Field(default="evolution", alias="WHATSAPP_PROVIDER")
    whatsapp_gateway_base_url: str = Field(default="", alias="WHATSAPP_GATEWAY_BASE_URL")
    whatsapp_gateway_api_key: str = Field(default="", alias="WHATSAPP_GATEWAY_API_KEY")
    whatsapp_session_name: str = Field(default="", alias="WHATSAPP_SESSION_NAME")
    evolution_api_base_url: str = Field(default="", alias="EVOLUTION_API_BASE_URL")
    evolution_api_key: str = Field(default="", alias="EVOLUTION_API_KEY")
    evolution_instance_name: str = Field(default="", alias="EVOLUTION_INSTANCE_NAME")
    instagram_business_account_id: str = Field(default="", alias="INSTAGRAM_BUSINESS_ACCOUNT_ID")
    instagram_app_id: str = Field(default="", alias="INSTAGRAM_APP_ID")
    instagram_app_secret: str = Field(default="", alias="INSTAGRAM_APP_SECRET")
    meta_app_id: str = Field(default="", alias="META_APP_ID")
    meta_app_secret: str = Field(default="", alias="META_APP_SECRET")
    meta_app_secret_previous: str = Field(default="", alias="META_APP_SECRET_PREVIOUS")
    meta_allow_unsigned_instagram: bool = Field(default=False, alias="META_ALLOW_UNSIGNED_INSTAGRAM")
    meta_oauth_redirect_uri: str = Field(default="", alias="META_OAUTH_REDIRECT_URI")
    meta_oauth_scopes: str = Field(
        default=(
            "public_profile,pages_show_list,pages_read_engagement,"
            "instagram_basic,instagram_content_publish,"
            "business_management,whatsapp_business_management,whatsapp_business_messaging"
        ),
        alias="META_OAUTH_SCOPES",
    )
    oauth_state_secret: str = Field(default="", alias="OAUTH_STATE_SECRET")
    oauth_state_ttl_seconds: int = Field(default=600, alias="OAUTH_STATE_TTL_SECONDS")
    token_encryption_secret: str = Field(default="", alias="TOKEN_ENCRYPTION_SECRET")
    youtube_api_key: str = Field(default="", alias="YOUTUBE_API_KEY")
    youtube_client_id: str = Field(default="", alias="YOUTUBE_CLIENT_ID")
    youtube_client_secret: str = Field(default="", alias="YOUTUBE_CLIENT_SECRET")
    tiktok_enabled: bool = Field(default=True, alias="TIKTOK_ENABLED")
    tiktok_api_base_url: str = Field(default="https://open.tiktokapis.com", alias="TIKTOK_API_BASE_URL")
    tiktok_client_key: str = Field(default="", alias="TIKTOK_CLIENT_KEY")
    tiktok_client_secret: str = Field(default="", alias="TIKTOK_CLIENT_SECRET")
    llm_enabled: bool = Field(default=True, alias="LLM_ENABLED")
    llm_provider: str = Field(default="ollama", alias="LLM_PROVIDER")
    llm_base_url: str = Field(default="http://127.0.0.1:11434", alias="LLM_BASE_URL")
    llm_model: str = Field(default="qwen2.5:0.5b-instruct", alias="LLM_MODEL")
    llm_temperature: float = Field(default=0.2, alias="LLM_TEMPERATURE")
    llm_max_output_tokens: int = Field(default=160, alias="LLM_MAX_OUTPUT_TOKENS")
    llm_timeout_seconds: float = Field(default=45.0, alias="LLM_TIMEOUT_SECONDS")
    llm_num_ctx: int = Field(default=768, alias="LLM_NUM_CTX")
    llm_num_thread: int = Field(default=2, alias="LLM_NUM_THREAD")
    llm_keep_alive: str = Field(default="8m", alias="LLM_KEEP_ALIVE")
    llm_business_open_hour: int = Field(default=9, alias="LLM_BUSINESS_OPEN_HOUR")
    llm_business_close_hour: int = Field(default=22, alias="LLM_BUSINESS_CLOSE_HOUR")
    llm_context_messages: int = Field(default=5, alias="LLM_CONTEXT_MESSAGES")
    llm_offtopic_tolerance_turns: int = Field(default=2, alias="LLM_OFFTOPIC_TOLERANCE_TURNS")
    llm_domain_lock: bool = Field(default=True, alias="LLM_DOMAIN_LOCK")
    llm_domain_description: str = Field(
        default="fc vip estudio fotografia video agendamento",
        alias="LLM_DOMAIN_DESCRIPTION",
    )
    llm_knowledge_path: str = Field(default="app/prompts/studio_agendamento.md", alias="LLM_KNOWLEDGE_PATH")
    llm_knowledge_max_chars: int = Field(default=5000, alias="LLM_KNOWLEDGE_MAX_CHARS")
    llm_knowledge_max_sections: int = Field(default=3, alias="LLM_KNOWLEDGE_MAX_SECTIONS")
    llm_prompt_max_context_chars: int = Field(default=700, alias="LLM_PROMPT_MAX_CONTEXT_CHARS")
    llm_max_key_memories: int = Field(default=12, alias="LLM_MAX_KEY_MEMORIES")
    llm_test_models: str = Field(
        default="qwen2.5:0.5b-instruct,qwen2.5:1.5b-instruct",
        alias="LLM_TEST_MODELS",
    )
    llm_quality_retry_enabled: bool = Field(default=True, alias="LLM_QUALITY_RETRY_ENABLED")
    llm_quality_fallback_model: str = Field(
        default="qwen2.5:1.5b-instruct",
        alias="LLM_QUALITY_FALLBACK_MODEL",
    )
    llm_quality_min_chars: int = Field(default=80, alias="LLM_QUALITY_MIN_CHARS")
    local_storage_path: str = Field(default="storage", alias="LOCAL_STORAGE_PATH")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @property
    def meta_ready(self) -> bool:
        return bool(self.meta_access_token.strip())

    @property
    def meta_runtime_enabled(self) -> bool:
        return self.meta_enabled and self.meta_ready

    @property
    def instagram_publish_ready(self) -> bool:
        return self.meta_runtime_enabled and bool(self.instagram_business_account_id.strip())

    @property
    def meta_oauth_ready(self) -> bool:
        return (
            self.meta_enabled
            and bool(self.effective_meta_app_id.strip())
            and bool(self.effective_meta_app_secret.strip())
        )

    @property
    def effective_oauth_state_secret(self) -> str:
        return (
            self.oauth_state_secret.strip()
            or self.effective_meta_app_secret.strip()
            or self.meta_verify_token.strip()
        )

    @property
    def effective_token_encryption_secret(self) -> str:
        return (
            self.token_encryption_secret.strip()
            or self.effective_meta_app_secret.strip()
            or self.meta_verify_token.strip()
        )

    @property
    def effective_meta_app_id(self) -> str:
        return self.meta_app_id.strip() or self.instagram_app_id.strip()

    @property
    def effective_meta_app_secret(self) -> str:
        return self.meta_app_secret.strip() or self.instagram_app_secret.strip()

    @property
    def tiktok_ready(self) -> bool:
        return bool(self.tiktok_client_key.strip()) and bool(self.tiktok_client_secret.strip())

    @property
    def tiktok_runtime_enabled(self) -> bool:
        return self.tiktok_enabled and self.tiktok_ready

    @property
    def normalized_whatsapp_provider(self) -> str:
        return str(self.whatsapp_provider or "evolution").strip().lower() or "evolution"

    @property
    def whatsapp_gateway_ready(self) -> bool:
        return bool(self.whatsapp_gateway_base_url.strip()) and bool(self.effective_whatsapp_session_name.strip())

    @property
    def effective_whatsapp_session_name(self) -> str:
        return self.whatsapp_session_name.strip() or self.evolution_instance_name.strip()

    @property
    def evolution_ready(self) -> bool:
        return (
            bool(self.evolution_api_base_url.strip())
            and bool(self.evolution_api_key.strip())
            and bool(self.evolution_instance_name.strip())
        )

    @property
    def whatsapp_dispatch_ready(self) -> bool:
        if self.normalized_whatsapp_provider == "baileys":
            return self.whatsapp_gateway_ready
        return self.evolution_ready

    @property
    def llm_ready(self) -> bool:
        return self.llm_enabled and bool(self.llm_model.strip()) and bool(self.llm_base_url.strip())

    @property
    def llm_test_models_list(self) -> list[str]:
        raw_items = [item.strip() for item in self.llm_test_models.split(",")]
        return [item for item in raw_items if item]

    @property
    def llm_effective_context_messages(self) -> int:
        desired = max(1, int(self.llm_context_messages))
        return max(3, min(5, desired))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
