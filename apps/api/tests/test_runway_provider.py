from types import SimpleNamespace
from typing import Any

import pytest

from app.config import Settings
from app.providers.base import ProviderInputImage, ProviderRequest
from app.providers.registry import configured_registry
from app.providers.runway import RunwayProvider


class FakeRunwayClient:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.deleted: list[str] = []
        self.status = "PENDING"
        self.output: list[str] | None = None
        self.poll_error: Exception | None = None
        self.image_to_video = SimpleNamespace(create=self.create)
        self.tasks = SimpleNamespace(retrieve=self.retrieve, delete=self.delete)

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.created.append(kwargs)
        return SimpleNamespace(id="runway-task-123")

    def retrieve(self, task_id: str) -> SimpleNamespace:
        assert task_id == "runway-task-123"
        if self.poll_error:
            raise self.poll_error
        return SimpleNamespace(status=self.status, output=self.output)

    def delete(self, task_id: str) -> None:
        self.deleted.append(task_id)


def settings(**changes: Any) -> Settings:
    return Settings(_env_file=None, local_auth_secret="test-secret-" * 8, **changes)


def request() -> ProviderRequest:
    return ProviderRequest(
        job_id="11111111-1111-4111-8111-111111111111",
        kind="video",
        action="scene",
        input_data={
            "scene_id": "22222222-2222-4222-8222-222222222222",
            "prompt": "Subtle breathing and a slow camera push-in.",
            "prompt_version": "scene-motion-v1",
            "model": "gen4_turbo",
            "duration_seconds": 5,
            "ratio": "832:1104",
        },
        attempt=0,
        idempotency_key="request-key",
        source_image=ProviderInputImage(
            asset_id="33333333-3333-4333-8333-333333333333",
            mime_type="image/png",
            content_base64="aGVsbG8=",
        ),
    )


def test_provider_uses_official_image_to_video_create_and_persistable_task_id() -> None:
    client = FakeRunwayClient()
    provider = RunwayProvider(settings(runwayml_api_secret="worker-only-secret"), client)

    submitted = provider.submit(request())

    assert submitted.status == "pending"
    assert submitted.provider_task_id == "runway-task-123"
    call = client.created[0]
    assert call["model"] == "gen4_turbo"
    assert call["prompt_image"] == "data:image/png;base64,aGVsbG8="
    assert call["duration"] == 5
    assert call["ratio"] == "832:1104"
    assert call["prompt_text"].startswith("Subtle breathing")


def test_provider_normalizes_pending_success_failure_and_cancellation() -> None:
    client = FakeRunwayClient()
    provider = RunwayProvider(settings(), client)
    initial = provider.submit(request())

    pending = provider.poll(initial.provider_task_id, request(), initial.state)
    assert pending.status == "pending"
    assert pending.poll_after_seconds is not None and pending.poll_after_seconds >= 5

    client.status = "SUCCEEDED"
    client.output = ["https://cdn.runwayml.com/output.mp4?temporary=secret"]
    completed = provider.poll(initial.provider_task_id, request(), pending.state)
    normalized = provider.normalize_result(completed, request())
    assert normalized.artifacts[0].source_url == client.output[0]
    assert normalized.artifacts[0].asset_type == "video"
    assert normalized.metadata["model"] == "gen4_turbo"

    client.status = "FAILED"
    failed = provider.poll(initial.provider_task_id, request(), pending.state)
    assert failed.status == "failed"
    assert failed.error_code == "runway_task_failed"

    client.status = "CANCELED"
    canceled = provider.poll(initial.provider_task_id, request(), pending.state)
    assert canceled.status == "canceled"
    assert canceled.error_code == "runway_task_canceled"
    provider.cancel(initial.provider_task_id)
    assert client.deleted == ["runway-task-123"]


@pytest.mark.parametrize(
    "model,duration,valid",
    [
        ("gen4_turbo", 5, True),
        ("gen4_turbo", 2, False),
        ("gen4.5", 2, True),
        ("gen4.5", 11, False),
    ],
)
def test_provider_checks_model_duration_before_call(model: str, duration: int, valid: bool) -> None:
    client = FakeRunwayClient()
    provider = RunwayProvider(settings(), client)
    payload = request().model_copy(
        update={
            "input_data": {
                **request().input_data,
                "model": model,
                "duration_seconds": duration,
            }
        }
    )

    result = provider.submit(payload)

    assert (result.status == "pending") is valid
    assert bool(client.created) is valid


def test_provider_avoids_ambiguous_submit_retry_but_retries_explicit_rate_limit() -> None:
    class StatusError(Exception):
        def __init__(self, code: int) -> None:
            self.status_code = code

    client = FakeRunwayClient()
    client.image_to_video.create = lambda **_: (_ for _ in ()).throw(  # type: ignore[method-assign]
        StatusError(504)
    )
    provider = RunwayProvider(settings(), client)
    unknown = provider.submit(request())
    assert unknown.error_code == "runway_submit_outcome_unknown"
    assert not unknown.retryable

    client.image_to_video.create = lambda **_: (_ for _ in ()).throw(StatusError(429))  # type: ignore[method-assign]
    limited = provider.submit(request())
    assert limited.error_code == "runway_rate_limit"
    assert limited.retryable


def test_provider_rejects_non_https_output_urls_and_missing_worker_key() -> None:
    client = FakeRunwayClient()
    provider = RunwayProvider(settings(), client)
    task = provider.submit(request())
    client.status = "SUCCEEDED"
    client.output = ["http://127.0.0.1/video.mp4"]
    result = provider.poll(task.provider_task_id, request(), task.state)
    with pytest.raises(Exception, match="unusable video URL"):
        provider.normalize_result(result, request())

    unavailable = RunwayProvider(settings())
    assert unavailable.submit(request()).error_code == "runway_configuration_error"


def test_registry_exposes_runway_for_configured_worker() -> None:
    registry = configured_registry(settings(runwayml_api_secret="worker-only-secret"))
    assert registry.resolve("runway").name == "runway"
