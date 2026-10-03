from __future__ import annotations

import ipaddress
import logging
import re
from collections.abc import Mapping
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
from pydantic import JsonValue

from app.config import Settings
from app.errors import ApplicationError, StorageError
from app.providers.base import (
    NormalizedProviderResult,
    ProviderArtifact,
    ProviderPollResult,
    ProviderRequest,
    ProviderResult,
    ProviderSubmitResult,
)

logger = logging.getLogger(__name__)
_MODEL_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*/[a-zA-Z0-9][a-zA-Z0-9._/-]*$")
_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
_ALLOWED_HOSTS = {"fal.media", "fal.ai", "storage.googleapis.com"}


class FalClient(Protocol):
    def submit(self, model: str, arguments: dict[str, Any]) -> str: ...

    def status(self, model: str, request_id: str) -> object: ...

    def result(self, model: str, request_id: str) -> object: ...

    def cancel(self, model: str, request_id: str) -> None: ...


class FalSdkClient:
    """Queue adapter using fal-client for polling/result/cancel and a single-shot submit."""

    def __init__(self, key: str, timeout_seconds: float) -> None:
        from fal_client import SyncClient

        self.sdk = SyncClient(key=key, default_timeout=timeout_seconds)
        self.key = key
        self.timeout_seconds = timeout_seconds

    def submit(self, model: str, arguments: dict[str, Any]) -> str:
        # fal-client's submit retries POST requests internally. Submit exactly once because
        # a timeout after queue acceptance can otherwise create duplicate paid generations.
        with httpx.Client(timeout=self.timeout_seconds, follow_redirects=False) as client:
            response = client.post(
                f"https://queue.fal.run/{model}",
                headers={
                    "Authorization": f"Key {self.key}",
                    "Content-Type": "application/json",
                },
                json=arguments,
            )
            response.raise_for_status()
            payload = response.json()
        request_id = payload.get("request_id") if isinstance(payload, dict) else None
        if not isinstance(request_id, str) or not request_id:
            raise ValueError("fal.ai did not return a queue request id")
        return request_id

    def status(self, model: str, request_id: str) -> object:
        return self.sdk.status(model, request_id)

    def result(self, model: str, request_id: str) -> object:
        return self.sdk.result(model, request_id)

    def cancel(self, model: str, request_id: str) -> None:
        self.sdk.cancel(model, request_id)


class FalProvider:
    """Queued fal.ai image adapter. It never stores output bytes outside Worker storage."""

    name = "fal"

    def __init__(
        self,
        settings: Settings,
        *,
        client: FalClient | None = None,
    ) -> None:
        self.settings = settings
        self.client = client
        if self.client is None and settings.fal_key:
            self.client = FalSdkClient(settings.fal_key, settings.openai_timeout_seconds)

    def submit(self, request: ProviderRequest) -> ProviderSubmitResult:
        model = self._model(request)
        if not self.settings.fal_key:
            return self._submit_failure(
                request,
                "fal_configuration_error",
                "fal.ai is not configured on the background worker.",
            )
        if self.client is None:
            return self._submit_failure(
                request,
                "fal_configuration_error",
                "fal.ai client is unavailable on the background worker.",
            )
        if request.kind not in {"image", "character"} or request.action not in {
            "scene",
            "reference",
        }:
            return self._submit_failure(
                request,
                "fal_invalid_request",
                "fal.ai currently supports image and character reference generation only.",
            )
        if not self._valid_model(model):
            return self._submit_failure(
                request,
                "fal_invalid_model",
                "The configured fal.ai model identifier is invalid.",
            )
        prompt = request.input_data.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            return self._submit_failure(
                request,
                "fal_invalid_request",
                "fal.ai image generation requires a prompt.",
            )
        if request.reference_images and model != self.settings.fal_reference_image_model:
            return self._submit_failure(
                request,
                "fal_invalid_model",
                "Reference images require the configured fal.ai reference model.",
            )
        arguments: dict[str, Any] = {
            "prompt": prompt,
            "image_size": {"width": 1024, "height": 1536},
        }
        if request.reference_images:
            # PuLID accepts one identity image. Other characters remain represented in the
            # composed Character Bible prompt and deterministic reference order.
            reference = request.reference_images[0]
            arguments["reference_image_url"] = (
                f"data:{reference.mime_type};base64,{reference.content_base64}"
            )
        elif model == self.settings.fal_image_model:
            arguments["output_format"] = "jpeg"

        used_references: list[JsonValue] = (
            [str(request.reference_images[0].asset_id)] if request.reference_images else []
        )
        try:
            task_id = self.client.submit(model, arguments)
        except Exception as exc:
            status = self._status_code(exc)
            code, message, retryable = self._classify(exc, phase="submit")
            logger.warning(
                "job=%s provider=fal model=%s phase=submit error=%s retryable=%s",
                request.job_id,
                model,
                code,
                retryable,
            )
            return ProviderSubmitResult(
                status="failed",
                provider_task_id="",
                state={"model": model, "http_status": status or 0},
                error_code=code,
                error_message=message,
                retryable=retryable,
            )
        if not isinstance(task_id, str) or not task_id:
            return self._submit_failure(
                request,
                "fal_request_id_missing",
                "fal.ai did not return a queue request identifier.",
            )
        metadata: dict[str, JsonValue] = {
            "model": model,
            "poll_count": 0,
            "reference_asset_ids": used_references,
            "reference_policy": "first_canonical_plus_bible_text",
        }
        logger.info(
            "job=%s provider=fal model=%s request_id=%s state=queued",
            request.job_id,
            model,
            task_id,
        )
        return ProviderSubmitResult(
            status="pending",
            provider_task_id=task_id,
            state=metadata,
            poll_after_seconds=self.settings.worker_provider_poll_seconds,
        )

    def poll(
        self,
        provider_task_id: str,
        request: ProviderRequest,
        state: dict[str, JsonValue],
    ) -> ProviderPollResult:
        model = self._persisted_model(request, state)
        if not self.settings.fal_key or self.client is None:
            return ProviderPollResult(
                status="failed",
                provider_task_id=provider_task_id,
                state=state,
                error_code="fal_configuration_error",
                error_message="fal.ai is not configured on the background worker.",
            )
        if not self._valid_model(model):
            return ProviderPollResult(
                status="failed",
                provider_task_id=provider_task_id,
                state=state,
                error_code="fal_invalid_model",
                error_message="The fal.ai model recorded for this job is invalid.",
            )
        try:
            status = self.client.status(model, provider_task_id)
            from fal_client import Completed, InProgress, Queued

            poll_count = self._integer(state.get("poll_count"), 0) + 1
            next_state: dict[str, JsonValue] = {**state, "poll_count": poll_count}
            if isinstance(status, (Queued, InProgress)):
                return ProviderPollResult(
                    status="pending",
                    provider_task_id=provider_task_id,
                    state=next_state,
                    poll_after_seconds=self._poll_delay(poll_count),
                )
            if not isinstance(status, Completed):
                return ProviderPollResult(
                    status="failed",
                    provider_task_id=provider_task_id,
                    state=next_state,
                    error_code="fal_unknown_status",
                    error_message="fal.ai returned an unknown queue status.",
                )
            if status.error:
                return ProviderPollResult(
                    status="failed",
                    provider_task_id=provider_task_id,
                    state=next_state,
                    error_code="fal_generation_failed",
                    error_message="fal.ai could not generate this image.",
                )
            result = self.client.result(model, provider_task_id)
            if not isinstance(result, dict):
                return ProviderPollResult(
                    status="failed",
                    provider_task_id=provider_task_id,
                    state=next_state,
                    error_code="fal_malformed_result",
                    error_message="fal.ai returned an invalid result structure.",
                )
            return ProviderPollResult(
                status="completed",
                provider_task_id=provider_task_id,
                state={
                    **next_state,
                    "result": result,
                    "model": model,
                    "provider_metrics": self._safe_metrics(status.metrics),
                },
            )
        except Exception as exc:
            code, message, retryable = self._classify(exc, phase="poll")
            logger.warning(
                "job=%s provider=fal model=%s phase=poll error=%s retryable=%s",
                request.job_id,
                model,
                code,
                retryable,
            )
            return ProviderPollResult(
                status="failed",
                provider_task_id=provider_task_id,
                state=state,
                error_code=code,
                error_message=message,
                retryable=retryable,
            )

    def cancel(self, provider_task_id: str, provider_model: str | None = None) -> None:
        if not self.settings.fal_key or self.client is None:
            raise ApplicationError(
                "fal.ai is not configured on the background worker.",
                "fal_configuration_error",
                503,
            )
        model = provider_model or self.settings.fal_image_model
        if not self._valid_model(model):
            raise ApplicationError(
                "The recorded fal.ai model is invalid.", "fal_invalid_model", 422
            )
        try:
            from fal_client import Completed, InProgress, Queued

            status = self.client.status(model, provider_task_id)
            if isinstance(status, Completed):
                return
            if isinstance(status, (Queued, InProgress)):
                self.client.cancel(model, provider_task_id)
        except Exception as exc:
            if self._status_code(exc) in {404, 409}:
                return
            raise ApplicationError(
                "fal.ai task cancellation failed", "fal_cancel_failed", 502
            ) from exc

    def normalize_result(
        self, result: ProviderResult, request: ProviderRequest
    ) -> NormalizedProviderResult:
        raw = result.state.get("result")
        if not isinstance(raw, dict):
            raise ApplicationError(
                "fal.ai returned a malformed image result", "fal_malformed_result", 502
            )
        images = raw.get("images")
        if not isinstance(images, list) or len(images) != 1 or not isinstance(images[0], dict):
            raise ApplicationError(
                "fal.ai must return exactly one image", "fal_malformed_result", 502
            )
        image = images[0]
        url = image.get("url")
        mime_type = image.get("content_type", "image/jpeg")
        if not isinstance(url, str) or not self._safe_output_url(url):
            raise ApplicationError(
                "fal.ai returned an unsafe or invalid image URL", "fal_invalid_output_url", 502
            )
        if mime_type not in _IMAGE_TYPES:
            raise ApplicationError(
                "fal.ai returned an unsupported image type", "invalid_image_content_type", 415
            )
        model = self._persisted_model(request, result.state)
        reference_ids = result.state.get("reference_asset_ids", [])
        metadata: dict[str, JsonValue] = {
            "provider": self.name,
            "model": model,
            "request_id": result.provider_task_id,
            "reference_asset_ids": reference_ids if isinstance(reference_ids, list) else [],
            "reference_policy": result.state.get(
                "reference_policy", "first_canonical_plus_bible_text"
            ),
        }
        metrics = result.state.get("provider_metrics")
        if isinstance(metrics, dict):
            metadata["provider_metrics"] = metrics
        width = self._positive_integer(image.get("width"))
        height = self._positive_integer(image.get("height"))
        return NormalizedProviderResult(
            kind=request.kind,
            output={"scene_id": request.input_data.get("scene_id", ""), "mock": False},
            artifacts=[
                ProviderArtifact(
                    asset_type="reference" if request.kind == "character" else "image",
                    mime_type=mime_type,
                    filename=(
                        "character-reference.jpg"
                        if request.kind == "character"
                        else "scene-image.jpg"
                    ),
                    source_url=url,
                    width=width,
                    height=height,
                    prompt=self._prompt(request),
                    metadata={"provider": self.name, "model": model},
                )
            ],
            metadata=metadata,
            mock=False,
        )

    def download_artifact(self, source_url: str, max_bytes: int) -> tuple[bytes, str]:
        url = source_url
        for redirect_count in range(4):
            if not self._safe_output_url(url):
                raise ApplicationError("fal.ai image URL is invalid", "fal_output_expired", 410)
            try:
                with httpx.stream(
                    "GET", url, timeout=httpx.Timeout(60.0, connect=10.0), follow_redirects=False
                ) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        if redirect_count == 3 or not response.headers.get("location"):
                            raise ApplicationError(
                                "fal.ai image URL redirected too many times",
                                "fal_output_expired",
                                410,
                            )
                        from urllib.parse import urljoin

                        url = urljoin(url, response.headers["location"])
                        continue
                    if response.status_code in {401, 403, 404, 410}:
                        raise ApplicationError(
                            "fal.ai temporary image has expired; generate a new image.",
                            "fal_output_expired",
                            410,
                        )
                    if response.status_code == 429 or response.status_code >= 500:
                        raise StorageError("fal.ai image download is temporarily unavailable")
                    response.raise_for_status()
                    mime_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                    if mime_type not in _IMAGE_TYPES:
                        raise ApplicationError(
                            "fal.ai returned a non-image file", "invalid_image_content_type", 415
                        )
                    content_length = response.headers.get("content-length")
                    if content_length and int(content_length) > max_bytes:
                        raise ApplicationError("Image is too large", "image_too_large", 413)
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if len(content) > max_bytes:
                            raise ApplicationError("Image is too large", "image_too_large", 413)
                    if not content:
                        raise ApplicationError(
                            "fal.ai returned an empty image", "invalid_image", 422
                        )
                    return bytes(content), mime_type
            except httpx.TimeoutException as exc:
                raise StorageError("fal.ai image download timed out") from exc
            except httpx.RequestError as exc:
                raise StorageError("fal.ai image download failed") from exc
        raise ApplicationError("fal.ai image URL is unusable", "fal_output_expired", 410)

    def _model(self, request: ProviderRequest) -> str:
        if request.provider_model:
            return request.provider_model
        if request.reference_images:
            return self.settings.fal_reference_image_model
        return self.settings.fal_image_model

    def _persisted_model(self, request: ProviderRequest, state: Mapping[str, JsonValue]) -> str:
        return request.provider_model or self._text(state.get("model"), self._model(request))

    @staticmethod
    def _valid_model(model: str) -> bool:
        return bool(_MODEL_RE.fullmatch(model)) and ".." not in model and not model.endswith("/")

    @staticmethod
    def _safe_output_url(value: str) -> bool:
        try:
            parsed = urlparse(value)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.port not in {None, 443}
                or not parsed.path.startswith("/")
            ):
                return False
            host = parsed.hostname.rstrip(".").lower()
            try:
                ipaddress.ip_address(host)
            except ValueError:
                return host in _ALLOWED_HOSTS or any(
                    host.endswith(f".{base}") for base in _ALLOWED_HOSTS
                )
            return False
        except ValueError:
            return False

    @staticmethod
    def _status_code(exc: Exception) -> int | None:
        response = getattr(exc, "response", None)
        response_code = getattr(response, "status_code", None)
        if isinstance(response_code, int):
            return response_code
        value = getattr(exc, "status_code", None)
        return value if isinstance(value, int) else None

    @classmethod
    def _classify(cls, exc: Exception, *, phase: str) -> tuple[str, str, bool]:
        status = cls._status_code(exc)
        if phase == "submit" and status is None:
            return (
                "fal_submit_outcome_unknown",
                "fal.ai submission outcome is unknown; the request was not automatically repeated.",
                False,
            )
        if status in {401, 403}:
            return "fal_authentication_error", "fal.ai rejected the worker credentials.", False
        if status in {400, 404, 422}:
            return "fal_invalid_request", "fal.ai rejected the image request or model.", False
        if status == 429:
            return "fal_rate_limit", "fal.ai is temporarily rate limited.", True
        if status in {408, 409} or (status is not None and status >= 500):
            return (
                "fal_provider_unavailable",
                "fal.ai is temporarily unavailable.",
                True if phase == "poll" else False,
            )
        if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
            return (
                "fal_timeout",
                "fal.ai could not be reached reliably.",
                phase == "poll",
            )
        if isinstance(exc, httpx.TransportError):
            return (
                "fal_connection_error",
                "fal.ai could not be reached reliably.",
                phase == "poll",
            )
        return "fal_provider_error", "fal.ai could not process the image request.", False

    def _submit_failure(
        self, request: ProviderRequest, code: str, message: str
    ) -> ProviderSubmitResult:
        logger.warning(
            "job=%s provider=fal model=%s error=%s",
            request.job_id,
            self._model(request),
            code,
        )
        return ProviderSubmitResult(
            status="failed",
            provider_task_id="",
            error_code=code,
            error_message=message,
        )

    @staticmethod
    def _poll_delay(poll_count: int) -> float:
        exponent = min(max(poll_count - 1, 0), 4)
        delay_seconds: float = float(2**exponent)
        return min(30.0, delay_seconds)

    @staticmethod
    def _integer(value: JsonValue | None, default: int) -> int:
        return value if isinstance(value, int) and not isinstance(value, bool) else default

    @staticmethod
    def _positive_integer(value: object) -> int | None:
        return (
            value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None
        )

    @staticmethod
    def _safe_metrics(value: object) -> dict[str, JsonValue]:
        if not isinstance(value, dict):
            return {}
        safe: dict[str, JsonValue] = {}
        for key, item in value.items():
            if (
                isinstance(key, str)
                and len(key) <= 80
                and isinstance(item, (int, float))
                and not isinstance(item, bool)
            ):
                safe[key] = item
        return safe

    @staticmethod
    def _prompt(request: ProviderRequest) -> str | None:
        value = request.input_data.get("prompt")
        return value if isinstance(value, str) else None

    @staticmethod
    def _text(value: JsonValue | None, default: str) -> str:
        return value.strip() if isinstance(value, str) and value.strip() else default
