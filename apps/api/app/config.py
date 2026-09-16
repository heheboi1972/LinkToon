from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../../.env", ".env"), extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    auth_mode: Literal["local", "supabase"] = "local"
    storage_provider: Literal["local", "supabase"] = "local"
    mock_ai: bool = True
    local_auth_secret: str = ""
    database_url: str = "sqlite:///./.data/linktoon.db"
    redis_url: str = "redis://localhost:6379/0"
    api_public_url: str = "http://localhost:8000"
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    local_storage_path: str = ".data/assets"
    max_upload_bytes: int = 10 * 1024 * 1024
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_storage_bucket: str = "linktoon-private"
    openai_api_key: str = ""
    fal_key: str = ""
    runwayml_api_secret: str = ""
    ai_quotas_enabled: bool = True
    story_daily_limit: int = Field(default=10, ge=1, le=1000)
    image_daily_limit: int = Field(default=5, ge=1, le=1000)
    motion_daily_limit: int = Field(default=2, ge=1, le=1000)

    @field_validator("api_public_url")
    @classmethod
    def normalize_api_url(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, values: list[str]) -> list[str]:
        origins = [value.rstrip("/") for value in values]
        if not origins or "*" in origins:
            raise ValueError("CORS_ORIGINS must list explicit web origins")
        for origin in origins:
            parsed = urlparse(origin)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path:
                raise ValueError("CORS_ORIGINS entries must be HTTP origins without paths")
        return origins

    @model_validator(mode="after")
    def validate_modes(self) -> "Settings":
        if (
            len(self.local_auth_secret) < 32
            or self.local_auth_secret == "GENERATE_WITH_SETUP_SCRIPT"
        ):
            raise ValueError("LOCAL_AUTH_SECRET must be a random string of at least 32 characters")
        if self.app_env == "production":
            if self.auth_mode != "supabase" or self.storage_provider != "supabase":
                raise ValueError("Production requires Supabase Auth and Storage")
            if self.database_url.startswith("sqlite"):
                raise ValueError("Production requires PostgreSQL")
            if not self.api_public_url.startswith("https://"):
                raise ValueError("Production API_PUBLIC_URL must use HTTPS")
            if any(not origin.startswith("https://") for origin in self.cors_origins):
                raise ValueError("Production CORS_ORIGINS must use HTTPS")
        if self.auth_mode == "supabase" and not (self.supabase_url and self.supabase_anon_key):
            raise ValueError("Supabase Auth configuration is missing")
        if self.storage_provider == "supabase" and not (
            self.supabase_url and self.supabase_service_role_key
        ):
            raise ValueError("Supabase Storage configuration is missing")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
