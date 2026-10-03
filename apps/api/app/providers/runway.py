from __future__ import annotations

import ipaddress
import random
from urllib.parse import urljoin, urlparse

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


class RunwayProvider:
    """Runway image-to-video adapter. It submits and polls only; Worker owns persistence."""

    name = "runway"

    def __init__(self, settings: Settings, client: object | None = None) -> None:
        self.settings = settings
        if client is None:
            if settings.runwayml_api_secret:
                try:
                    from runwayml import RunwayML
                except ImportError as exc:
                    raise ApplicationError(
                        "Runway SDK is not installed", "runway_configuration_error", 503
                    ) from exc
                client = RunwayML(
                    api_key=settings.runwayml_api_secret,
                    runway_version=settings.runway_api_version,
                    max_retries=0,
                    timeout=settings.openai_timeout_seconds,
                )
        self.client = client

    def submit(self, request: ProviderRequest) -> ProviderSubmitResult:
        if self.client is None:
            return ProviderSubmitResult(
                status="failed",
                provider_task_id="",
                error_code="runway_configuration_error",
                error_message="Runway is not configured on the background worker.",
            )
        if request.kind != "video" or request.action != "scene" or request.source_image is None:
            return ProviderSubmitResult(
                status="failed",
                provider_task_id="",
                error_code="runway_invalid_request",
                error_message="A prepared Scene image is required for motion generation.",
            )
        model = self._text(request.input_data.get("model"), self.settings.runway_video_model)
        duration = self._integer(
            request.input_data.get("duration_seconds"), self.settings.runway_video_duration_seconds
        )
        ratio = self._text(request.input_data.get("ratio"), "832:1104")
        if not self._valid_model_duration(model, duration) or ratio not in {
            "1280:720",
            "720:1280",
            "1104:832",
            "832:1104",
            "960:960",
            "1584:672",
        }:
            return ProviderSubmitResult(
                status="failed",
                provider_task_id="",
                error_code="runway_invalid_request",
                error_message="The selected Runway video settings are not supported.",
            )
        image_uri = (
            f"data:{request.source_image.mime_type};base64,{request.source_image.content_base64}"
        )
        try:
            response = self.client.image_to_video.create(  # type: ignore[attr-defined]
                model=model,
                prompt_image=image_uri,
                prompt_text=self._text(request.input_data.get("prompt"), "Subtle motion."),
                duration=duration,
                ratio=ratio,
            )
        except Exception as exc:
            # The API has no documented task-creation idempotency key. A timeout can
            # happen after Runway accepted the paid request, so never resubmit blindly.
            status = self._status_code(exc)
            if status == 401:
                code, message = "runway_authentication_error", "Runway rejected the API key."
            elif status == 400:
                code, message = "runway_invalid_request", "Runway rejected the video request."
            elif status == 429:
                code, message = "runway_rate_limit", "Runway is temporarily rate limited."
            elif status is not None and status >= 500:
                code, message = (
                    "runway_submit_outcome_unknown",
                    "Runway's response was unavailable.",
                )
            else:
                code, message = (
                    "runway_submit_outcome_unknown",
                    "Runway request outcome is unknown.",
                )
            return ProviderSubmitResult(
                status="failed",
                provider_task_id="",
                error_code=code,
                error_message=message,
                retryable=status == 429,
            )
        task_id = getattr(response, "id", None)
        if not isinstance(task_id, str) or not task_id:
            return ProviderSubmitResult(
                status="failed",
                provider_task_id="",
                error_code="runway_task_id_missing",
                error_message="Runway did not return a task identifier.",
            )
        return ProviderSubmitResult(
            status="pending",
            provider_task_id=task_id,
            poll_after_seconds=5.0 + random.uniform(0.0, 1.25),
            state={
                "runway_status": "PENDING",
                "poll_count": 0,
                "model": model,
                "duration_seconds": duration,
                "ratio": ratio,
                "prompt_version": self._text(
                    request.input_data.get("prompt_version"), "scene-motion-v1"
                ),
            },
        )

    def poll(
        self,
        provider_task_id: str,
        request: ProviderRequest,
        state: dict[str, JsonValue],
    ) -> ProviderPollResult:
        if self.client is None:
            return ProviderPollResult(
                status="failed",
                provider_task_id=provider_task_id,
                state=state,
                error_code="runway_configuration_error",
                error_message="Runway is not configured on the background worker.",
            )
        try:
            task = self.client.tasks.retrieve(provider_task_id)  # type: ignore[attr-defined]
        except Exception as exc:
            response_status = self._status_code(exc)
            if response_status in {400, 401, 404}:
                return ProviderPollResult(
                    status="failed",
                    provider_task_id=provider_task_id,
                    state=state,
                    error_code="runway_poll_request_failed",
                    error_message="Runway could not find or authorize this task.",
                )
            return ProviderPollResult(
                status="failed",
                provider_task_id=provider_task_id,
                state=state,
                error_code="runway_poll_unavailable",
                error_message="Runway task status could not be checked.",
                retryable=True,
            )
        status = str(getattr(task, "status", "")).upper()
        polls = self._integer(state.get("poll_count"), 0) + 1
        next_state: dict[str, JsonValue] = {
            **state,
            "runway_status": status,
            "poll_count": polls,
        }
        if status in {"PENDING", "RUNNING", "THROTTLED"}:
            base = min(60.0, 5.0 * (2 ** min(polls - 1, 4)))
            return ProviderPollResult(
                status="pending",
                provider_task_id=provider_task_id,
                state=next_state,
                poll_after_seconds=base + random.uniform(0.0, min(5.0, base * 0.25)),
            )
        if status in {"CANCELED", "CANCELLED"}:
            return ProviderPollResult(
                status="canceled",
                provider_task_id=provider_task_id,
                state=next_state,
                error_code="runway_task_canceled",
                error_message="Runway canceled the motion task.",
            )
        if status == "FAILED":
            return ProviderPollResult(
                status="failed",
                provider_task_id=provider_task_id,
                state=next_state,
                error_code="runway_task_failed",
                error_message="Runway could not generate this motion preview.",
            )
        if status != "SUCCEEDED":
            return ProviderPollResult(
                status="failed",
                provider_task_id=provider_task_id,
                state=next_state,
                error_code="runway_unknown_status",
                error_message="Runway returned an unknown task status.",
            )
        output = getattr(task, "output", None)
        output_url = output[0] if isinstance(output, (list, tuple)) and output else output
        if not isinstance(output_url, str) or not output_url:
            return ProviderPollResult(
                status="failed",
                provider_task_id=provider_task_id,
                state=next_state,
                error_code="runway_output_missing",
                error_message="Runway completed without a downloadable video.",
            )
        return ProviderPollResult(
            status="completed",
            provider_task_id=provider_task_id,
            state={**next_state, "output_url": output_url},
        )

    def cancel(self, provider_task_id: str, provider_model: str | None = None) -> None:
        if self.client is None:
            raise ApplicationError(
                "Runway is not configured on the background worker.",
                "runway_configuration_error",
                503,
            )
        try:
            self.client.tasks.delete(provider_task_id)  # type: ignore[attr-defined]
        except Exception as exc:
            if self._status_code(exc) not in {404, 409}:
                raise ApplicationError(
                    "Runway task cancellation failed", "runway_cancel_failed", 502
                ) from exc

    def normalize_result(
        self, result: ProviderResult, request: ProviderRequest
    ) -> NormalizedProviderResult:
        output_url = result.state.get("output_url")
        if not isinstance(output_url, str) or not self._safe_https_url(output_url):
            raise ApplicationError(
                "Runway returned an unusable video URL", "runway_output_missing", 502
            )
        return NormalizedProviderResult(
            kind="video",
            output={"scene_id": request.input_data.get("scene_id", ""), "mock": False},
            artifacts=[
                ProviderArtifact(
                    asset_type="video",
                    mime_type="video/mp4",
                    filename="scene-motion.mp4",
                    source_url=output_url,
                    duration_ms=self._integer(request.input_data.get("duration_seconds"), 5) * 1000,
                    prompt=self._text(request.input_data.get("prompt"), ""),
                    metadata={
                        "model": self._text(request.input_data.get("model"), "gen4_turbo"),
                        "ratio": self._text(request.input_data.get("ratio"), ""),
                        "prompt_version": self._text(
                            request.input_data.get("prompt_version"), "scene-motion-v1"
                        ),
                    },
                )
            ],
            metadata={
                "provider": "runway",
                "model": self._text(request.input_data.get("model"), "gen4_turbo"),
                "duration_seconds": self._integer(request.input_data.get("duration_seconds"), 5),
                "ratio": self._text(request.input_data.get("ratio"), ""),
                "runway_status": result.state.get("runway_status", "SUCCEEDED"),
            },
            mock=False,
        )

    def download_artifact(self, source_url: str, max_bytes: int) -> tuple[bytes, str]:
        url = source_url
        for redirect_count in range(4):
            if not self._safe_https_url(url):
                raise ApplicationError(
                    "Runway video download URL is invalid", "runway_output_expired", 410
                )
            try:
                with httpx.stream(
                    "GET", url, timeout=httpx.Timeout(60.0, connect=10.0), follow_redirects=False
                ) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        if redirect_count == 3:
                            raise ApplicationError(
                                "Runway video URL redirected too many times",
                                "runway_output_expired",
                                410,
                            )
                        location = response.headers.get("location")
                        if not location:
                            raise ApplicationError(
                                "Runway video URL redirect is invalid",
                                "runway_output_expired",
                                410,
                            )
                        url = urljoin(url, location)
                        continue
                    if response.status_code in {401, 403, 404, 410}:
                        raise ApplicationError(
                            "Runway's temporary video has expired; generate a new preview.",
                            "runway_output_expired",
                            410,
                        )
                    if response.status_code == 429 or response.status_code >= 500:
                        raise StorageError("Runway video download is temporarily unavailable")
                    response.raise_for_status()
                    mime_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                    if mime_type != "video/mp4":
                        raise ApplicationError(
                            "Runway returned a non-MP4 video", "invalid_video_content_type", 415
                        )
                    length = response.headers.get("content-length")
                    if length and int(length) > max_bytes:
                        raise ApplicationError("Video is too large", "video_too_large", 413)
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if len(content) > max_bytes:
                            raise ApplicationError("Video is too large", "video_too_large", 413)
                    if not content:
                        raise ApplicationError(
                            "Runway returned an empty video", "invalid_video", 422
                        )
                    return bytes(content), mime_type
            except httpx.TimeoutException as exc:
                raise StorageError("Runway video download timed out") from exc
            except httpx.RequestError as exc:
                raise StorageError("Runway video download failed") from exc
        raise ApplicationError("Runway video URL is unusable", "runway_output_expired", 410)

    @staticmethod
    def _safe_https_url(value: str) -> bool:
        try:
            parsed = urlparse(value)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.port not in {None, 443}
            ):
                return False
            host = parsed.hostname.rstrip(".").lower()
            if host in {"localhost", "metadata.google.internal"} or host.endswith(".localhost"):
                return False
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                return "." in host
            return address.is_global
        except ValueError:
            return False

    @staticmethod
    def _status_code(exc: Exception) -> int | None:
        value = getattr(exc, "status_code", None)
        return value if isinstance(value, int) else None

    @staticmethod
    def _integer(value: JsonValue | None, default: int) -> int:
        return value if isinstance(value, int) and not isinstance(value, bool) else default

    @staticmethod
    def _text(value: JsonValue | None, default: str) -> str:
        return value.strip() if isinstance(value, str) and value.strip() else default

    @staticmethod
    def _valid_model_duration(model: str, duration: int) -> bool:
        return (
            duration in {5, 10}
            if model == "gen4_turbo"
            else (2 <= duration <= 10 if model == "gen4.5" else False)
        )
