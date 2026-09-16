from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Signup(Input):
    email: EmailStr
    password: Annotated[str, StringConstraints(strip_whitespace=False)] = Field(
        min_length=10, max_length=128
    )
    display_name: str = Field(min_length=1, max_length=80)


class Login(Input):
    email: EmailStr
    password: Annotated[str, StringConstraints(strip_whitespace=False)] = Field(
        min_length=1, max_length=128
    )


class ProfileOut(Output):
    id: UUID
    email: str
    display_name: str


class SessionOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: ProfileOut


class ProjectCreate(Input):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=5000)
    genre: str = Field(default="fantasy", min_length=1, max_length=50)
    orientation: Literal["vertical", "horizontal"] = "vertical"
    creation_mode: Literal["manual", "assisted", "ai_first"] = "manual"
    visual_style: str = Field(default="cinematic", min_length=1, max_length=100)


class Patch(Input):
    @model_validator(mode="after")
    def reject_null(self) -> "Patch":
        nullable = {"image_asset_id", "thumbnail_asset_id"}
        for field in self.model_fields_set - nullable:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class ProjectPatch(Patch):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=5000)
    genre: str | None = Field(default=None, min_length=1, max_length=50)
    status: Literal["draft", "active", "archived"] | None = None
    thumbnail_asset_id: UUID | None = None


class ProjectOut(Output):
    id: UUID
    owner_id: UUID
    title: str
    description: str
    genre: str
    orientation: str
    creation_mode: str
    status: str
    thumbnail_asset_id: UUID | None
    created_at: datetime
    updated_at: datetime


class BibleOut(Output):
    project_id: UUID
    story_bible: dict[str, Any]
    world_bible: dict[str, Any]
    visual_bible: dict[str, Any]
    prompt_rules: list[str]
    negative_rules: list[str]


class EpisodeCreate(Input):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=5000)


class EpisodePatch(Patch):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=5000)


class EpisodeOut(Output):
    id: UUID
    project_id: UUID
    number: int
    title: str
    description: str
    status: str
    created_at: datetime
    updated_at: datetime


class PanelCreate(Input):
    title: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=5000)
    dialogue: str = Field(default="", max_length=5000)
    image_asset_id: UUID | None = None


class PanelPatch(Patch):
    title: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=5000)
    dialogue: str | None = Field(default=None, max_length=5000)
    image_asset_id: UUID | None = None


class PanelOut(Output):
    id: UUID
    episode_id: UUID
    position: int
    title: str
    description: str
    dialogue: str
    image_asset_id: UUID | None
    status: str
    created_at: datetime
    updated_at: datetime


class UploadRequest(Input):
    project_id: UUID
    filename: str = Field(min_length=1, max_length=200)
    mime_type: Literal["image/png", "image/jpeg", "image/webp"]
    file_size: int = Field(gt=0)
    asset_type: Literal["image", "reference", "thumbnail"] = "image"


class UploadTicket(BaseModel):
    asset_id: UUID
    upload_url: str
    method: str = "PUT"
    expires_in: int = 900


class UploadComplete(Input):
    asset_id: UUID


class AssetOut(Output):
    id: UUID
    owner_id: UUID
    project_id: UUID
    asset_type: str
    mime_type: str
    storage_provider: str
    storage_key: str
    public_url: str | None
    thumbnail_url: str | None
    width: int | None
    height: int | None
    duration_ms: int | None
    file_size: int
    metadata: dict[str, Any]
    upload_status: str
    created_at: datetime


class JobOut(Output):
    id: UUID
    project_id: UUID
    job_type: str
    status: str
    progress: int
    error_message: str | None
    created_at: datetime


class QuotaBucket(BaseModel):
    limit: int
    used: int
    remaining: int


class QuotaOut(BaseModel):
    enabled: bool
    reset_at: datetime
    buckets: dict[str, QuotaBucket]
