from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

type GenerationKind = Literal["story", "image", "character", "video"]
type ProviderStatus = Literal["completed", "pending", "failed", "canceled"]
type ArtifactType = Literal["image", "video", "audio", "reference"]


class ProviderModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProviderReferenceImage(ProviderModel):
    character_id: UUID
    asset_id: UUID
    mime_type: str
    content_base64: str


class ProviderInputImage(ProviderModel):
    asset_id: UUID
    mime_type: str
    content_base64: str


class ProviderRequest(ProviderModel):
    job_id: UUID
    kind: GenerationKind
    action: str
    provider_model: str | None = None
    input_data: dict[str, JsonValue]
    attempt: int = Field(ge=0)
    idempotency_key: str
    reference_images: list[ProviderReferenceImage] = Field(default_factory=list, max_length=4)
    source_image: ProviderInputImage | None = None


class ProviderArtifact(ProviderModel):
    asset_type: ArtifactType
    mime_type: str
    filename: str
    content_base64: str | None = None
    source_url: str | None = None
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    duration_ms: int | None = Field(default=None, gt=0)
    prompt: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class NormalizedProviderResult(ProviderModel):
    kind: GenerationKind
    output: dict[str, JsonValue]
    artifacts: list[ProviderArtifact] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    mock: bool = False


class ProviderSubmitResult(ProviderModel):
    status: ProviderStatus
    provider_task_id: str
    state: dict[str, JsonValue] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    poll_after_seconds: float | None = Field(default=None, gt=0, le=300)


class ProviderPollResult(ProviderModel):
    status: ProviderStatus
    provider_task_id: str
    state: dict[str, JsonValue] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    poll_after_seconds: float | None = Field(default=None, gt=0, le=300)


type ProviderResult = ProviderSubmitResult | ProviderPollResult


class GenerationProvider(Protocol):
    name: str

    def submit(self, request: ProviderRequest) -> ProviderSubmitResult: ...

    def poll(
        self,
        provider_task_id: str,
        request: ProviderRequest,
        state: dict[str, JsonValue],
    ) -> ProviderPollResult: ...

    def cancel(self, provider_task_id: str, provider_model: str | None = None) -> None: ...

    def normalize_result(
        self, result: ProviderResult, request: ProviderRequest
    ) -> NormalizedProviderResult: ...
