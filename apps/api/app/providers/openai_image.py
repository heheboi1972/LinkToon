"""OpenAI Image API capability used by the composite OpenAI provider."""

import base64
import binascii
import logging
from io import BytesIO
from typing import Any, Protocol

import openai
from pydantic import JsonValue, ValidationError

from app.config import Settings
from app.errors import GenerationError
from app.image_generation import CharacterReferenceProviderInput, SceneImageProviderInput
from app.providers.base import (
    NormalizedProviderResult,
    ProviderArtifact,
    ProviderRequest,
    ProviderResult,
    ProviderSubmitResult,
)

logger = logging.getLogger(__name__)


class ImagesAPI(Protocol):
    def generate(self, **kwargs: Any) -> object: ...

    def edit(self, **kwargs: Any) -> object: ...


class ImageOpenAIClient(Protocol):
    images: ImagesAPI


class OpenAIImageCapability:
    """Synchronous one-prompt Image API adapter; storage remains a Worker concern."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def submit(self, request: ProviderRequest, client: ImageOpenAIClient) -> ProviderSubmitResult:
        try:
            image_input = (
                CharacterReferenceProviderInput.model_validate(request.input_data)
                if request.kind == "character"
                else SceneImageProviderInput.model_validate(request.input_data)
            )
        except ValidationError:
            return self._failed(
                request,
                "openai_invalid_request",
                "Image generation input is invalid.",
                retryable=False,
            )
        try:
            model = self._model(request)
            common = {
                "model": model,
                "prompt": image_input.prompt,
                "n": 1,
                "size": self.settings.openai_image_size,
                "quality": self.settings.openai_image_quality,
                "output_format": self.settings.openai_image_format,
                "extra_headers": {"X-Client-Request-Id": f"{request.job_id}:{request.attempt}"},
            }
            if request.reference_images:
                files = []
                for reference in request.reference_images:
                    raw = base64.b64decode(reference.content_base64, validate=True)
                    stream = BytesIO(raw)
                    stream.name = f"{reference.asset_id}.{reference.mime_type.split('/')[-1]}"
                    files.append(stream)
                response = client.images.edit(
                    image=files,
                    input_fidelity="high",
                    response_format="b64_json",
                    **common,
                )
            else:
                response = client.images.generate(**common)
        except openai.OpenAIError as exc:
            return self._openai_failure(request, exc)

        request_id = self._text_attribute(response, "_request_id")
        data = getattr(response, "data", None)
        item = data[0] if isinstance(data, (list, tuple)) and len(data) == 1 else None
        encoded = self._text_attribute(item, "b64_json") if item is not None else None
        if not encoded or not self._valid_base64_size(encoded):
            return self._failed(
                request,
                "openai_invalid_image_response",
                "OpenAI returned an invalid or oversized image response.",
                retryable=False,
                request_id=request_id,
            )
        metadata = self._metadata(response, request, request_id)
        revised_prompt = self._text_attribute(item, "revised_prompt")
        if revised_prompt:
            metadata["revised_prompt"] = revised_prompt
        provider_task_id = request_id or f"openai-image-{request.job_id}"
        logger.info(
            "job=%s provider=openai model=%s request_id=%s state=completed format=%s size=%s",
            request.job_id,
            metadata.get("model"),
            request_id,
            metadata.get("format"),
            metadata.get("size"),
        )
        return ProviderSubmitResult(
            status="completed",
            provider_task_id=provider_task_id,
            state={
                "image_base64": encoded,
                "prompt": image_input.prompt,
                "metadata": metadata,
            },
        )

    def normalize_result(
        self, result: ProviderResult, request: ProviderRequest
    ) -> NormalizedProviderResult:
        if request.kind not in {"image", "character"} or result.status != "completed":
            raise GenerationError("OpenAI result is not a completed image")
        try:
            image_input = (
                CharacterReferenceProviderInput.model_validate(request.input_data)
                if request.kind == "character"
                else SceneImageProviderInput.model_validate(request.input_data)
            )
        except ValidationError as exc:
            raise GenerationError("OpenAI image input is invalid") from exc
        encoded = result.state.get("image_base64")
        metadata_value = result.state.get("metadata", {})
        if not isinstance(encoded, str) or not self._valid_base64_size(encoded):
            raise GenerationError("OpenAI image content is invalid or oversized")
        metadata = metadata_value if isinstance(metadata_value, dict) else {}
        output_format = metadata.get("format", self.settings.openai_image_format)
        if not isinstance(output_format, str) or output_format not in {"png", "jpeg", "webp"}:
            raise GenerationError("OpenAI image format is unsupported")
        mime_type = {
            "png": "image/png",
            "jpeg": "image/jpeg",
            "webp": "image/webp",
        }.get(output_format)
        if mime_type is None:
            raise GenerationError("OpenAI image format is unsupported")
        width, height = self._dimensions(self.settings.openai_image_size)
        if request.kind == "character":
            assert isinstance(image_input, CharacterReferenceProviderInput)
            output = {
                "character_id": str(image_input.character_id),
                "reference_asset_id": None,
                "message": "Character reference generated.",
            }
        else:
            assert isinstance(image_input, SceneImageProviderInput)
            output = {"scene_id": str(image_input.scene_id), "message": "Scene image generated."}
        return NormalizedProviderResult(
            kind=request.kind,
            output=output,
            artifacts=[
                ProviderArtifact(
                    asset_type="image",
                    mime_type=mime_type,
                    filename=("character-reference" if request.kind == "character" else "scene")
                    + f".{output_format}",
                    content_base64=encoded,
                    width=width,
                    height=height,
                    prompt=image_input.prompt,
                    metadata=metadata,
                )
            ],
            metadata=metadata,
        )

    def configuration_error(self, request: ProviderRequest) -> ProviderSubmitResult | None:
        if not self._model(request).strip():
            return self._failed(
                request,
                "openai_configuration_error",
                "OpenAI image model is not configured for the worker.",
                retryable=False,
            )
        return None

    def _valid_base64_size(self, encoded: str) -> bool:
        maximum_encoded = ((self.settings.max_upload_bytes + 2) // 3) * 4 + 4
        if len(encoded) > maximum_encoded:
            return False
        try:
            return bool(base64.b64decode(encoded, validate=True))
        except (binascii.Error, ValueError):
            return False

    def _openai_failure(
        self, request: ProviderRequest, exc: openai.OpenAIError
    ) -> ProviderSubmitResult:
        request_id = self._text_attribute(exc, "request_id")
        if isinstance(exc, openai.AuthenticationError):
            code, message, retryable = (
                "openai_authentication_error",
                "OpenAI rejected the configured API credentials.",
                False,
            )
        elif isinstance(
            exc,
            (
                openai.BadRequestError,
                openai.PermissionDeniedError,
                openai.NotFoundError,
                openai.UnprocessableEntityError,
            ),
        ):
            code, message, retryable = (
                "openai_invalid_request",
                "OpenAI rejected the Scene image request or model configuration.",
                False,
            )
        elif isinstance(exc, openai.RateLimitError):
            code, message = "openai_rate_limit", "OpenAI rate-limited the Scene image request."
            retryable = self._text_attribute(exc, "code") not in {
                "credit_balance_exhausted",
                "organization_spend_limit_exceeded",
                "project_spend_limit_exceeded",
                "organization_usage_limit_exceeded",
                "insufficient_quota",
            }
        elif isinstance(exc, openai.APITimeoutError):
            code, message, retryable = (
                "openai_timeout",
                "OpenAI Scene image generation timed out.",
                True,
            )
        elif isinstance(exc, openai.InternalServerError):
            code, message, retryable = (
                "openai_server_error",
                "OpenAI temporarily failed to generate the Scene image.",
                True,
            )
        elif isinstance(exc, openai.APIConnectionError):
            code, message, retryable = (
                "openai_connection_error",
                "The worker could not connect to OpenAI.",
                True,
            )
        elif isinstance(exc, openai.APIStatusError):
            retryable = exc.status_code in {408, 409, 429} or exc.status_code >= 500
            code = "openai_server_error" if retryable else "openai_invalid_request"
            message = (
                "OpenAI temporarily failed to generate the Scene image."
                if retryable
                else "OpenAI rejected the Scene image request."
            )
        else:
            code, message, retryable = (
                "openai_provider_error",
                "OpenAI could not process the Scene image request.",
                False,
            )
        return self._failed(
            request,
            code,
            message,
            retryable=retryable,
            request_id=request_id,
        )

    def _failed(
        self,
        request: ProviderRequest,
        code: str,
        message: str,
        *,
        retryable: bool,
        request_id: str | None = None,
    ) -> ProviderSubmitResult:
        metadata: dict[str, JsonValue] = {
            "provider": "openai",
            "model": self._model(request),
            "client_request_id": f"{request.job_id}:{request.attempt}",
        }
        if request_id:
            metadata["request_id"] = request_id
        logger.warning(
            "job=%s provider=openai model=%s request_id=%s error_type=%s retryable=%s",
            request.job_id,
            self._model(request),
            request_id,
            code,
            retryable,
        )
        return ProviderSubmitResult(
            status="failed",
            provider_task_id=request_id or f"openai-image-error-{request.job_id}",
            state={"metadata": metadata},
            error_code=code,
            error_message=message,
            retryable=retryable,
        )

    def _metadata(
        self, response: object, request: ProviderRequest, request_id: str | None
    ) -> dict[str, JsonValue]:
        metadata: dict[str, JsonValue] = {
            "provider": "openai",
            "model": self._model(request),
            "client_request_id": f"{request.job_id}:{request.attempt}",
            "size": self._text_attribute(response, "size") or self.settings.openai_image_size,
            "quality": (
                self._text_attribute(response, "quality") or self.settings.openai_image_quality
            ),
            "format": (
                self._text_attribute(response, "output_format") or self.settings.openai_image_format
            ),
        }
        if request_id:
            metadata["request_id"] = request_id
        usage = getattr(response, "usage", None)
        if usage is not None:
            for attribute in ("input_tokens", "output_tokens", "total_tokens"):
                value = getattr(usage, attribute, None)
                if isinstance(value, int) and not isinstance(value, bool):
                    metadata[attribute] = value
        return metadata

    def _model(self, request: ProviderRequest) -> str:
        if request.provider_model:
            return request.provider_model
        if request.kind == "character" or request.reference_images:
            return self.settings.openai_image_reference_model
        return self.settings.openai_image_model

    @staticmethod
    def _dimensions(value: str) -> tuple[int, int]:
        width, height = value.split("x", 1)
        return int(width), int(height)

    @staticmethod
    def _text_attribute(value: object, name: str) -> str | None:
        attribute = getattr(value, name, None)
        return attribute if isinstance(attribute, str) and attribute else None
