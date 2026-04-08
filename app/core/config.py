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
    meta_verify_token: str = Field(default="change-me", alias="META_VERIFY_TOKEN")
    meta_access_token: str = Field(default="", alias="META_ACCESS_TOKEN")
    instagram_app_id: str = Field(default="", alias="INSTAGRAM_APP_ID")
    instagram_app_secret: str = Field(default="", alias="INSTAGRAM_APP_SECRET")
    youtube_client_id: str = Field(default="", alias="YOUTUBE_CLIENT_ID")
    youtube_client_secret: str = Field(default="", alias="YOUTUBE_CLIENT_SECRET")
    tiktok_client_key: str = Field(default="", alias="TIKTOK_CLIENT_KEY")
    tiktok_client_secret: str = Field(default="", alias="TIKTOK_CLIENT_SECRET")
    local_storage_path: str = Field(default="storage", alias="LOCAL_STORAGE_PATH")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
