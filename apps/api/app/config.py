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
    openai_story_model: str = "gpt-5.6-terra"
    openai_image_model: str = "gpt-image-2.5-flare"
    openai_image_reference_model: str = "gpt-image-2.5-sunburst"
    openai_image_size: str = "1024x1536"
    openai_image_quality: Literal["low", "medium", "high", "xhigh", "max"] = "low"
    openai_image_format: Literal["png", "jpeg", "webp"] = "webp"
    openai_timeout_seconds: float = Field(default=90.0, gt=0, le=300)
    fal_key: str = ""
    image_provider: Literal["openai", "fal"] = "openai"
    fal_image_model: str = "fal-ai/flux-2-pro"
    fal_reference_image_model: str = "fal-ai/flux-pulid"
    runwayml_api_secret: str = ""
    runway_video_model: Literal["gen4_turbo", "gen4.5"] = "gen4_turbo"
    runway_video_duration_seconds: int = Field(default=5, ge=2, le=10)
    runway_api_version: str = "2024-11-06"
    max_video_bytes: int = Field(default=100 * 1024 * 1024, ge=1024, le=1024 * 1024 * 1024)
    ai_quotas_enabled: bool = True
    story_daily_limit: int = Field(default=10, ge=1, le=1000)
    image_daily_limit: int = Field(default=5, ge=1, le=1000)
    motion_daily_limit: int = Field(default=2, ge=1, le=1000)
    worker_id: str = Field(default="", max_length=100)
    worker_poll_interval_seconds: float = Field(default=2.0, ge=0.1, le=60)
    worker_lease_seconds: int = Field(default=120, ge=10, le=3600)
    worker_batch_size: int = Field(default=10, ge=1, le=100)
    worker_max_retries: int = Field(default=3, ge=0, le=20)
    worker_retry_base_seconds: float = Field(default=2.0, ge=0.1, le=300)
    worker_provider_poll_seconds: float = Field(default=2.0, ge=0.1, le=300)

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

    @field_validator("openai_image_size")
    @classmethod
    def validate_image_size(cls, value: str) -> str:
        try:
            width_text, height_text = value.lower().split("x", 1)
            width, height = int(width_text), int(height_text)
        except (ValueError, TypeError) as exc:
            raise ValueError("OPENAI_IMAGE_SIZE must use WIDTHxHEIGHT") from exc
        pixels = width * height
        ratio = width / height
        if (
            width % 16
            or height % 16
            or max(width, height) > 3840
            or not 1 / 3 <= ratio <= 3
            or not 655_360 <= pixels <= 8_294_400
        ):
            raise ValueError("OPENAI_IMAGE_SIZE is outside GPT Image limits")
        return f"{width}x{height}"

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
        if self.runway_video_model == "gen4_turbo" and self.runway_video_duration_seconds not in {
            5,
            10,
        }:
            raise ValueError("Gen-4 Turbo duration must be 5 or 10 seconds")
        if not self.runway_api_version.strip():
            raise ValueError("RUNWAY_API_VERSION must not be empty")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
