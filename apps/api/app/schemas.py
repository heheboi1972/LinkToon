from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_serializer,
    model_validator,
)


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


class CharacterOut(Output):
    id: UUID
    project_id: UUID
    name: str
    description: str
    appearance: str
    personality: str
    clothing: str
    prompt_token: str
    character_bible: dict[str, Any]
    appearance_lock: dict[str, Any]
    style_lock: dict[str, Any]
    primary_asset_id: UUID | None
    reference_asset_id: UUID | None
    reference_media_url: str | None = None
    reference_stale: bool
    character_revision: int
    reference_generated_from_revision: int | None
    created_at: datetime
    updated_at: datetime


class CharacterCreate(Input):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=5000)
    appearance: str = Field(default="", max_length=5000)
    personality: str = Field(default="", max_length=5000)
    clothing: str = Field(default="", max_length=2000)
    prompt_token: str = Field(default="", max_length=100)
    age_range: str = Field(default="", max_length=100)
    gender_presentation: str = Field(default="", max_length=100)
    face_description: str = Field(default="", max_length=2000)
    hair_description: str = Field(default="", max_length=2000)
    eye_description: str = Field(default="", max_length=1000)
    body_description: str = Field(default="", max_length=2000)
    accessories_description: str = Field(default="", max_length=2000)
    visual_style: str = Field(default="", max_length=1000)
    appearance_lock: dict[str, Any] = Field(default_factory=dict)
    style_lock: dict[str, Any] = Field(default_factory=dict)


class CharacterPatch(Patch):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=5000)
    appearance: str | None = Field(default=None, max_length=5000)
    personality: str | None = Field(default=None, max_length=5000)
    clothing: str | None = Field(default=None, max_length=2000)
    prompt_token: str | None = Field(default=None, max_length=100)
    age_range: str | None = Field(default=None, max_length=100)
    gender_presentation: str | None = Field(default=None, max_length=100)
    face_description: str | None = Field(default=None, max_length=2000)
    hair_description: str | None = Field(default=None, max_length=2000)
    eye_description: str | None = Field(default=None, max_length=1000)
    body_description: str | None = Field(default=None, max_length=2000)
    accessories_description: str | None = Field(default=None, max_length=2000)
    visual_style: str | None = Field(default=None, max_length=1000)
    appearance_lock: dict[str, Any] | None = None
    style_lock: dict[str, Any] | None = None


class CharacterReferenceSelect(Input):
    asset_id: UUID


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


class SceneOut(Output):
    id: UUID
    episode_id: UUID
    position: int
    title: str
    image_asset_id: UUID | None
    video_asset_id: UUID | None
    created_at: datetime
    updated_at: datetime


class ReaderDialogueOut(BaseModel):
    character: str
    text: str


class ReaderSceneOut(BaseModel):
    id: UUID
    order: int
    title: str
    narration: str
    dialogue: list[ReaderDialogueOut]
    image_url: str | None
    video_url: str | None


class EpisodeReaderOut(BaseModel):
    episode_id: UUID
    project_id: UUID
    number: int
    title: str
    summary: str
    scenes: list[ReaderSceneOut]


class PublicationPatch(Input):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=5000)
    visibility: Literal["private", "unlisted", "public"] | None = None

    @model_validator(mode="after")
    def has_changes(self) -> "PublicationPatch":
        if not self.model_fields_set:
            raise ValueError("At least one publication field must be provided")
        return self


class PublicationCreate(Input):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=5000)
    visibility: Literal["private", "unlisted", "public"] = "public"


class PublicationOut(BaseModel):
    id: UUID
    project_id: UUID
    episode_id: UUID
    slug: str
    title: str
    description: str
    visibility: Literal["private", "unlisted", "public"]
    status: Literal["published", "unpublished"]
    current_version: int
    published_at: datetime | None
    scene_count: int
    image_count: int
    motion_count: int


class PublicationSceneOut(BaseModel):
    order: int
    title: str
    narration: str
    dialogue: list[ReaderDialogueOut]
    image_url: str | None
    video_url: str | None


class PublicationReaderOut(BaseModel):
    slug: str
    title: str
    description: str
    author_name: str
    visibility: Literal["unlisted", "public"]
    published_at: datetime
    scene_count: int
    scenes: list[PublicationSceneOut]


class ProjectOverviewOut(BaseModel):
    project_id: UUID
    episode_count: int
    scene_count: int
    image_count: int
    motion_count: int
    character_count: int
    character_reference_count: int
    published_count: int
    latest_scene_image_url: str | None
    latest_scene_title: str | None
    updated_at: datetime


class StoryGenerationRequest(Input):
    idea: str = Field(min_length=1, max_length=10_000)
    genre: str | None = Field(default=None, min_length=1, max_length=50)
    tone: str = Field(default="cinematic", min_length=1, max_length=100)
    theme: str = Field(default="", max_length=500)
    characters: list[UUID] = Field(default_factory=list, max_length=20)
    scene_count: int = Field(default=6, ge=1, le=20)

    @model_validator(mode="after")
    def unique_characters(self) -> "StoryGenerationRequest":
        if len(self.characters) != len(set(self.characters)):
            raise ValueError("characters must not contain duplicates")
        return self


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
    storage_bucket: str | None
    storage_key: str
    source: str
    generation_job_id: UUID | None
    prompt: str | None
    public_url: str | None
    thumbnail_url: str | None
    width: int | None
    height: int | None
    duration_ms: int | None
    file_size: int
    metadata: dict[str, Any]
    upload_status: str
    created_at: datetime

    @field_serializer("metadata")
    def hide_provider_metadata(self, value: dict[str, Any]) -> dict[str, Any]:
        private_keys = {"provider", "model", "provider_task_id", "provider_metadata"}
        return {key: item for key, item in value.items() if key not in private_keys}


GenerationJobStatus = Literal[
    "queued", "running", "provider_pending", "saving", "succeeded", "failed", "canceled"
]


class JobAccepted(BaseModel):
    job_id: UUID
    status: GenerationJobStatus


class JobOut(Output):
    id: UUID
    project_id: UUID
    job_type: str
    status: GenerationJobStatus
    progress: int
    retry_count: int
    next_poll_at: datetime | None
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    cancel_requested_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @field_serializer("error_code")
    def hide_provider_error_code(self, value: str | None) -> str | None:
        if value and value.split("_", 1)[0] in {"openai", "runway", "fal"}:
            return "provider_error"
        return value

    @field_serializer("error_message")
    def hide_provider_error_message(self, value: str | None) -> str | None:
        if self.error_code and self.error_code.split("_", 1)[0] in {"openai", "runway", "fal"}:
            return "The AI service could not complete this generation."
        return value


class JobDetailOut(JobOut):
    input: dict[str, Any]
    output: dict[str, Any]
    cost_estimate: float | None
    cost_actual: float | None

    @field_serializer("input")
    def hide_provider_input_metadata(self, value: dict[str, Any]) -> dict[str, Any]:
        private_keys = {"model", "provider", "provider_task_id", "provider_metadata"}
        return {key: item for key, item in value.items() if key not in private_keys}

    @field_serializer("output")
    def hide_provider_output_metadata(self, value: dict[str, Any]) -> dict[str, Any]:
        return {key: item for key, item in value.items() if key != "provider_metadata"}


class QuotaBucket(BaseModel):
    limit: int
    used: int
    remaining: int


class QuotaOut(BaseModel):
    enabled: bool
    reset_at: datetime
    buckets: dict[str, QuotaBucket]
