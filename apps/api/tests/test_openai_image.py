import base64
import os
from io import BytesIO
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import httpx2
import openai
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings, get_settings
from app.job_worker import DatabaseWorker
from app.main import app
from app.models import Asset, GenerationJob, Scene
from app.providers.base import ProviderRequest
from app.providers.openai import OpenAIProvider
from app.providers.registry import ProviderRegistry, configured_registry


class FakeImages:
    def __init__(self, response: object | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def generate(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


class FakeOpenAIImageClient:
    def __init__(self, images: FakeImages) -> None:
        self.images = images
        self.responses = SimpleNamespace()


def settings(**changes: object) -> Settings:
    values: dict[str, object] = {
        "mock_ai": False,
        "openai_api_key": "test-api-key",
        "openai_image_model": "test-image-model",
        "openai_image_size": "1024x1536",
        "openai_image_quality": "low",
        "openai_image_format": "webp",
        "openai_timeout_seconds": 5,
        "worker_retry_base_seconds": 0.1,
        "worker_lease_seconds": 10,
    }
    values.update(changes)
    return Settings(_env_file=None, **values)


def webp_base64(size: tuple[int, int] = (32, 48)) -> str:
    output = BytesIO()
    Image.new("RGB", size, "#6d28d9").save(output, "WEBP")
    return base64.b64encode(output.getvalue()).decode("ascii")


def response(encoded: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        _request_id="req_image_123",
        data=[SimpleNamespace(b64_json=encoded or webp_base64(), revised_prompt="revised scene")],
        output_format="webp",
        quality="low",
        size="1024x1536",
        usage=SimpleNamespace(input_tokens=40, output_tokens=500, total_tokens=540),
    )


def request(*, attempt: int = 0) -> ProviderRequest:
    return ProviderRequest.model_validate(
        {
            "job_id": uuid4(),
            "kind": "image",
            "action": "scene",
            "input_data": {
                "scene_id": str(uuid4()),
                "episode_id": str(uuid4()),
                "prompt": "A moonlit rooftop scene in a polished webtoon style",
            },
            "attempt": attempt,
            "idempotency_key": "image-request-1",
        }
    )


def api_error(error_type: type[openai.APIStatusError], status: int) -> openai.APIStatusError:
    http_request = httpx2.Request("POST", "https://api.openai.com/v1/images/generations")
    http_response = httpx2.Response(
        status, request=http_request, headers={"x-request-id": "req_image_error"}
    )
    return error_type("provider failed", response=http_response, body=None)


def test_registry_resolves_openai_image_capability() -> None:
    provider = configured_registry(settings()).resolve("openai")
    image_request = request()
    assert isinstance(provider, OpenAIProvider)
    assert image_request.kind == "image"


def test_openai_image_uses_installed_sdk_contract_and_normalizes_base64() -> None:
    image_request = request()
    images = FakeImages(response())
    provider = OpenAIProvider(settings(), client=FakeOpenAIImageClient(images))

    submitted = provider.submit(image_request)
    normalized = provider.normalize_result(submitted, image_request)

    assert submitted.status == "completed"
    assert submitted.provider_task_id == "req_image_123"
    assert normalized.kind == "image"
    assert len(normalized.artifacts) == 1
    artifact = normalized.artifacts[0]
    assert artifact.mime_type == "image/webp"
    assert artifact.content_base64 == response().data[0].b64_json
    assert artifact.prompt == image_request.input_data["prompt"]
    assert normalized.metadata["request_id"] == "req_image_123"
    assert normalized.metadata["model"] == "test-image-model"
    assert normalized.metadata["total_tokens"] == 540
    call = images.calls[0]
    assert call == {
        "model": "test-image-model",
        "prompt": image_request.input_data["prompt"],
        "n": 1,
        "size": "1024x1536",
        "quality": "low",
        "output_format": "webp",
        "extra_headers": {"X-Client-Request-Id": f"{image_request.job_id}:0"},
    }


def test_invalid_openai_image_response_is_non_retryable() -> None:
    image_request = request()
    invalid = SimpleNamespace(_request_id="req_invalid", data=[])
    provider = OpenAIProvider(settings(), client=FakeOpenAIImageClient(FakeImages(invalid)))
    submitted = provider.submit(image_request)
    assert submitted.status == "failed"
    assert submitted.error_code == "openai_invalid_image_response"
    assert submitted.retryable is False


def test_missing_api_key_or_image_model_never_calls_image_api() -> None:
    images = FakeImages(response())
    missing_key = OpenAIProvider(
        settings(openai_api_key=""), client=FakeOpenAIImageClient(images)
    ).submit(request())
    missing_model = OpenAIProvider(
        settings(openai_image_model=""), client=FakeOpenAIImageClient(images)
    ).submit(request())
    assert missing_key.error_code == "openai_configuration_error"
    assert missing_model.error_code == "openai_configuration_error"
    assert images.calls == []


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (api_error(openai.RateLimitError, 429), "openai_rate_limit"),
        (
            openai.APITimeoutError(
                request=httpx2.Request("POST", "https://api.openai.com/v1/images/generations")
            ),
            "openai_timeout",
        ),
        (api_error(openai.InternalServerError, 500), "openai_server_error"),
    ],
)
def test_transient_openai_image_errors_are_retryable(error: Exception, expected_code: str) -> None:
    provider = OpenAIProvider(settings(), client=FakeOpenAIImageClient(FakeImages(error=error)))
    submitted = provider.submit(request(attempt=1))
    assert submitted.status == "failed"
    assert submitted.error_code == expected_code
    assert submitted.retryable is True


def configure_openai_image(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("MOCK_AI", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setenv("OPENAI_IMAGE_MODEL", "test-image-model")
    monkeypatch.setenv("OPENAI_IMAGE_SIZE", "1024x1536")
    monkeypatch.setenv("OPENAI_IMAGE_QUALITY", "low")
    monkeypatch.setenv("OPENAI_IMAGE_FORMAT", "webp")
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("WORKER_RETRY_BASE_SECONDS", "0.1")
    monkeypatch.setenv("WORKER_LEASE_SECONDS", "10")
    get_settings.cache_clear()
    return get_settings()


def create_scene(episode_id: str) -> UUID:
    with app.state.session_factory() as db:
        scene = Scene(
            episode_id=UUID(episode_id),
            position=0,
            title="Image scene",
            script={
                "visual_prompt": "A moonlit rooftop scene",
                "narration": "The city glows below.",
                "dialogue": [],
                "character_ids": [],
            },
        )
        db.add(scene)
        db.commit()
        return scene.id


def test_fake_openai_image_runs_worker_storage_asset_and_scene_pipeline(
    client: TestClient,
    headers: dict[str, str],
    episode: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = configure_openai_image(monkeypatch)
    scene_id = create_scene(episode["id"])
    accepted = client.post(
        f"/api/v1/scenes/{scene_id}/image/generate",
        headers={**headers, "Idempotency-Key": "fake-openai-image"},
    )
    assert accepted.status_code == 202
    images = FakeImages(response())
    provider = OpenAIProvider(configured, client=FakeOpenAIImageClient(images))
    worker = DatabaseWorker(
        app.state.session_factory,
        configured,
        ProviderRegistry([provider]),
        "fake-openai-image-worker",
    )
    assert worker.run_once()

    job_id = UUID(accepted.json()["job_id"])
    with app.state.session_factory() as db:
        job = db.get(GenerationJob, job_id)
        scene = db.get(Scene, scene_id)
        assert job is not None and job.status == "succeeded"
        assert job.provider == "openai" and job.provider_model == "test-image-model"
        assert scene is not None and scene.image_asset_id is not None
        asset = db.get(Asset, scene.image_asset_id)
        assert asset is not None
        assert asset.mime_type == "image/webp"
        assert asset.width == 32 and asset.height == 48
        assert asset.provider == "openai"
        assert asset.generation_job_id == job_id
        assert asset.metadata_json["request_id"] == "req_image_123"
        assert job.output["asset_id"] == str(asset.id)
    assert len(images.calls) == 1


@pytest.mark.skipif(
    os.getenv("RUN_OPENAI_INTEGRATION_TESTS", "").lower() != "true"
    or not os.getenv("OPENAI_API_KEY"),
    reason="Explicit OpenAI image smoke-test opt-in is required",
)
def test_opt_in_live_openai_image_smoke() -> None:
    configured = Settings(_env_file=None, mock_ai=False, openai_timeout_seconds=120)
    result = OpenAIProvider(configured).submit(request())
    assert result.status == "completed", result.error_code
