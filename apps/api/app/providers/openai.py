import logging
from collections.abc import Callable
from typing import Any, Protocol, cast

import openai
from openai import OpenAI
from pydantic import JsonValue, ValidationError

from app.config import Settings
from app.errors import GenerationError
from app.providers.base import (
    NormalizedProviderResult,
    ProviderPollResult,
    ProviderRequest,
    ProviderResult,
    ProviderSubmitResult,
)
from app.providers.openai_image import ImageOpenAIClient, ImagesAPI, OpenAIImageCapability
from app.story_generation import (
    STORY_DEVELOPER_INSTRUCTIONS,
    StoryProviderInput,
    StoryResult,
    allowed_character_ids,
    story_user_content,
    validate_story_result,
)

logger = logging.getLogger(__name__)


class ResponsesAPI(Protocol):
    def parse(self, **kwargs: Any) -> object: ...


class OpenAIClient(ImageOpenAIClient, Protocol):
    responses: ResponsesAPI
    images: ImagesAPI


ClientFactory = Callable[[str, float], OpenAIClient]


class OpenAIProvider:
    """Composite synchronous adapter for OpenAI Story and Scene image capabilities."""

    name = "openai"

    def __init__(
        self,
        settings: Settings,
        *,
        client: OpenAIClient | None = None,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self.settings = settings
        self._configured_client = client
        self._client_factory = client_factory or self._default_client
        self._image = OpenAIImageCapability(settings)

    @staticmethod
    def _default_client(api_key: str, timeout_seconds: float) -> OpenAIClient:
        # Worker retry policy is the single retry authority, so SDK retries stay disabled.
        return cast(
            OpenAIClient,
            OpenAI(api_key=api_key, max_retries=0, timeout=timeout_seconds),
        )

    def submit(self, request: ProviderRequest) -> ProviderSubmitResult:
        configuration_error = self._configuration_error(request)
        if configuration_error is not None:
            return configuration_error
        if request.kind in {"image", "character"}:
            return self._image.submit(request, self._client())
        if request.kind != "story":
            return self._failed(
                request,
                "openai_invalid_request",
                "OpenAIProvider currently supports Story generation only.",
                retryable=False,
            )
        try:
            story_input = StoryProviderInput.model_validate(request.input_data)
        except ValidationError:
            return self._failed(
                request,
                "openai_invalid_request",
                "Story generation input is invalid.",
                retryable=False,
            )

        try:
            client = self._client()
            response = client.responses.parse(
                model=request.provider_model or self.settings.openai_story_model,
                instructions=STORY_DEVELOPER_INSTRUCTIONS,
                input=[{"role": "user", "content": story_user_content(story_input)}],
                text_format=StoryResult,
                store=False,
                extra_headers={"X-Client-Request-Id": f"{request.job_id}:{request.attempt}"},
            )
        except openai.OpenAIError as exc:
            return self._openai_failure(request, exc)
        except ValidationError:
            return self._failed(
                request,
                "openai_invalid_structured_output",
                "OpenAI returned a Story that failed schema validation.",
                retryable=False,
            )

        response_id = self._text_attribute(response, "id")
        request_id = self._text_attribute(response, "_request_id")
        if not response_id:
            return self._failed(
                request,
                "openai_invalid_response",
                "OpenAI returned a response without an identifier.",
                retryable=False,
                request_id=request_id,
            )
        status = self._text_attribute(response, "status")
        if status != "completed":
            return self._failed(
                request,
                "openai_incomplete_response",
                "OpenAI did not complete the structured Story response.",
                retryable=False,
                request_id=request_id,
                provider_task_id=response_id,
            )
        try:
            parsed = getattr(response, "output_parsed", None)
            story = validate_story_result(
                parsed,
                scene_count=story_input.scene_count,
                allowed_ids=allowed_character_ids(story_input),
            )
        except GenerationError:
            return self._failed(
                request,
                "openai_invalid_structured_output",
                "OpenAI returned a Story that failed domain validation.",
                retryable=False,
                request_id=request_id,
                provider_task_id=response_id,
            )

        metadata = self._metadata(response, request, request_id)
        metadata["response_id"] = response_id
        logger.info(
            "job=%s provider=openai model=%s request_id=%s state=completed "
            "input_tokens=%s output_tokens=%s total_tokens=%s",
            request.job_id,
            metadata.get("model"),
            metadata.get("request_id"),
            metadata.get("input_tokens"),
            metadata.get("output_tokens"),
            metadata.get("total_tokens"),
        )
        return ProviderSubmitResult(
            status="completed",
            provider_task_id=response_id,
            state={
                "result": story.model_dump(mode="json"),
                "metadata": metadata,
            },
        )

    def poll(
        self,
        provider_task_id: str,
        request: ProviderRequest,
        state: dict[str, JsonValue],
    ) -> ProviderPollResult:
        return ProviderPollResult(
            status="failed",
            provider_task_id=provider_task_id,
            state=state,
            error_code="openai_poll_unsupported",
            error_message="Synchronous OpenAI Story jobs cannot be polled.",
            retryable=False,
        )

    def cancel(self, provider_task_id: str, provider_model: str | None = None) -> None:
        # Story requests complete synchronously before a task id is persisted.
        return None

    def normalize_result(
        self, result: ProviderResult, request: ProviderRequest
    ) -> NormalizedProviderResult:
        if request.kind in {"image", "character"}:
            return self._image.normalize_result(result, request)
        if request.kind != "story" or result.status != "completed":
            raise GenerationError("OpenAI result is not a completed Story")
        try:
            story_input = StoryProviderInput.model_validate(request.input_data)
            story = validate_story_result(
                result.state.get("result"),
                scene_count=story_input.scene_count,
                allowed_ids=allowed_character_ids(story_input),
            )
        except ValidationError as exc:
            raise GenerationError("OpenAI Story input is invalid") from exc
        metadata_value = result.state.get("metadata", {})
        metadata = metadata_value if isinstance(metadata_value, dict) else {}
        return NormalizedProviderResult(
            kind="story",
            output=story.model_dump(mode="json"),
            metadata=metadata,
        )

    def _configuration_error(self, request: ProviderRequest) -> ProviderSubmitResult | None:
        if not self.settings.openai_api_key.strip():
            return self._failed(
                request,
                "openai_configuration_error",
                "OPENAI_API_KEY is not configured for the worker.",
                retryable=False,
            )
        if request.kind in {"image", "character"}:
            return self._image.configuration_error(request)
        if request.kind == "story" and not self.settings.openai_story_model.strip():
            return self._failed(
                request,
                "openai_configuration_error",
                "OPENAI_STORY_MODEL is not configured for the worker.",
                retryable=False,
            )
        return None

    def _client(self) -> OpenAIClient:
        return self._configured_client or self._client_factory(
            self.settings.openai_api_key,
            self.settings.openai_timeout_seconds,
        )

    def _openai_failure(
        self, request: ProviderRequest, exc: openai.OpenAIError
    ) -> ProviderSubmitResult:
        request_id = self._text_attribute(exc, "request_id")
        if isinstance(exc, openai.AuthenticationError):
            code = "openai_authentication_error"
            message = "OpenAI rejected the configured API credentials."
            retryable = False
        elif isinstance(
            exc,
            (
                openai.BadRequestError,
                openai.PermissionDeniedError,
                openai.NotFoundError,
                openai.UnprocessableEntityError,
            ),
        ):
            code = "openai_invalid_request"
            message = "OpenAI rejected the Story generation request or model configuration."
            retryable = False
        elif isinstance(exc, openai.RateLimitError):
            code = "openai_rate_limit"
            message = "OpenAI rate-limited the Story generation request."
            retryable = self._text_attribute(exc, "code") not in {
                "credit_balance_exhausted",
                "organization_spend_limit_exceeded",
                "project_spend_limit_exceeded",
                "organization_usage_limit_exceeded",
                "insufficient_quota",
            }
        elif isinstance(exc, openai.APITimeoutError):
            code = "openai_timeout"
            message = "OpenAI Story generation timed out."
            retryable = True
        elif isinstance(exc, openai.InternalServerError):
            code = "openai_server_error"
            message = "OpenAI temporarily failed to generate the Story."
            retryable = True
        elif isinstance(exc, openai.APIConnectionError):
            code = "openai_connection_error"
            message = "The worker could not connect to OpenAI."
            retryable = True
        elif isinstance(exc, openai.APIStatusError):
            retryable = exc.status_code in {408, 409, 429} or exc.status_code >= 500
            code = "openai_server_error" if retryable else "openai_invalid_request"
            message = (
                "OpenAI temporarily failed to generate the Story."
                if retryable
                else "OpenAI rejected the Story generation request."
            )
        else:
            code = "openai_provider_error"
            message = "OpenAI could not process the Story generation request."
            retryable = False
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
        provider_task_id: str | None = None,
    ) -> ProviderSubmitResult:
        model = (
            self._image._model(request)
            if request.kind in {"image", "character"}
            else request.provider_model or self.settings.openai_story_model
        )
        metadata: dict[str, JsonValue] = {
            "provider": "openai",
            "model": model,
            "client_request_id": f"{request.job_id}:{request.attempt}",
        }
        if request_id:
            metadata["request_id"] = request_id
        logger.warning(
            "job=%s provider=openai model=%s request_id=%s error_type=%s retryable=%s",
            request.job_id,
            model,
            request_id,
            code,
            retryable,
        )
        return ProviderSubmitResult(
            status="failed",
            provider_task_id=provider_task_id or request_id or f"openai-error-{request.job_id}",
            state={"metadata": metadata},
            error_code=code,
            error_message=message,
            retryable=retryable,
        )

    def _metadata(
        self,
        response: object,
        request: ProviderRequest,
        request_id: str | None,
    ) -> dict[str, JsonValue]:
        metadata: dict[str, JsonValue] = {
            "provider": "openai",
            "model": self._text_attribute(response, "model")
            or request.provider_model
            or self.settings.openai_story_model,
            "client_request_id": f"{request.job_id}:{request.attempt}",
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

    @staticmethod
    def _text_attribute(value: object, name: str) -> str | None:
        attribute = getattr(value, name, None)
        return attribute if isinstance(attribute, str) and attribute else None
