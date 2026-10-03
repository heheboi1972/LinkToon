import os
import time
from datetime import timedelta
from io import BytesIO
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from conftest import upload_asset
from fal_client import Completed, InProgress, Queued
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.errors import ApplicationError, StorageError
from app.job_worker import DatabaseWorker, JobProcessor
from app.main import app
from app.models import Asset, Character, GenerationJob, Scene, utcnow
from app.providers.base import ProviderReferenceImage, ProviderRequest
from app.providers.fal import FalProvider
from app.providers.registry import ProviderRegistry
from app.services import GenerationService


class FakeFalClient:
    def __init__(self) -> None:
        self.submit_calls: list[tuple[str, dict[str, Any]]] = []
        self.statuses: list[object] = []
        self.result_value: object = {}
        self.cancel_calls: list[tuple[str, str]] = []

    def submit(self, model: str, arguments: dict[str, Any]) -> str:
        self.submit_calls.append((model, arguments))
        return "fal-request-123"

    def status(self, model: str, request_id: str) -> object:
        assert request_id == "fal-request-123"
        assert self.statuses
        return self.statuses.pop(0)

    def result(self, model: str, request_id: str) -> object:
        assert request_id == "fal-request-123"
        return self.result_value

    def cancel(self, model: str, request_id: str) -> None:
        self.cancel_calls.append((model, request_id))


class FailOnceStorage:
    def __init__(self) -> None:
        self.failures = 1
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, content: bytes, mime_type: str) -> None:
        if self.failures:
            self.failures -= 1
            raise StorageError("temporary object write failure")
        if key in self.objects:
            raise StorageError("immutable object already exists")
        self.objects[key] = content

    def read(self, key: str) -> bytes:
        try:
            return self.objects[key]
        except KeyError as exc:
            raise StorageError("object not found") from exc

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)


def settings(**changes: object) -> Settings:
    values: dict[str, object] = {
        "local_auth_secret": "fal-test-secret-" * 3,
        "app_env": "test",
        "mock_ai": False,
        "image_provider": "fal",
        "fal_key": "test-fal-key",
        "worker_provider_poll_seconds": 0.1,
        "worker_retry_base_seconds": 0.1,
        "worker_lease_seconds": 10,
    }
    values.update(changes)
    return Settings(_env_file=None, **values)


def provider_request(*, references: list[ProviderReferenceImage] | None = None) -> ProviderRequest:
    return ProviderRequest(
        job_id=uuid4(),
        kind="image",
        action="scene",
        provider_model="fal-ai/flux-pulid" if references else "fal-ai/flux-2-pro",
        input_data={"scene_id": str(uuid4()), "prompt": "A quiet moonlit rooftop."},
        attempt=0,
        idempotency_key="fal-test-intent",
        reference_images=references or [],
    )


def completed() -> Completed:
    return Completed(
        logs=None,
        metrics={"inference_time": 1.25, "sample_count": 1},
        error=None,
        error_type=None,
    )


def png_bytes() -> bytes:
    result = BytesIO()
    Image.new("RGB", (32, 48), "#743ad5").save(result, "PNG")
    return result.getvalue()


def test_fal_queue_submit_poll_result_and_reference_policy() -> None:
    first = ProviderReferenceImage(
        character_id=uuid4(), asset_id=uuid4(), mime_type="image/png", content_base64="YWJj"
    )
    second = ProviderReferenceImage(
        character_id=uuid4(), asset_id=uuid4(), mime_type="image/jpeg", content_base64="ZGVm"
    )
    request = provider_request(references=[first, second])
    client = FakeFalClient()
    client.statuses = [Queued(position=2), InProgress(logs=None), completed()]
    client.result_value = {
        "images": [
            {
                "url": "https://storage.googleapis.com/fal-output/scene.png",
                "content_type": "image/png",
                "width": 32,
                "height": 48,
            }
        ],
        "seed": 17,
    }
    provider = FalProvider(settings(), client=client)

    submitted = provider.submit(request)
    assert submitted.status == "pending"
    assert submitted.provider_task_id == "fal-request-123"
    assert client.submit_calls[0][0] == "fal-ai/flux-pulid"
    arguments = client.submit_calls[0][1]
    assert arguments["reference_image_url"] == "data:image/png;base64,YWJj"
    assert "YWJj" not in str(submitted.state)
    assert "ZGVm" not in str(submitted.state)
    assert submitted.state["reference_policy"] == "first_canonical_plus_bible_text"

    queued = provider.poll(submitted.provider_task_id, request, submitted.state)
    running = provider.poll(submitted.provider_task_id, request, queued.state)
    done = provider.poll(submitted.provider_task_id, request, running.state)
    normalized = provider.normalize_result(done, request)

    assert queued.status == "pending"
    assert running.status == "pending"
    assert done.status == "completed"
    assert normalized.metadata["provider"] == "fal"
    assert normalized.metadata["request_id"] == "fal-request-123"
    assert normalized.artifacts[0].source_url == client.result_value["images"][0]["url"]
    assert normalized.artifacts[0].mime_type == "image/png"
    assert normalized.artifacts[0].width == 32
    assert normalized.metadata["provider_metrics"] == {"inference_time": 1.25, "sample_count": 1}


def test_fal_missing_key_is_non_retryable_and_does_not_submit() -> None:
    client = FakeFalClient()
    provider = FalProvider(settings(fal_key=""), client=client)

    result = provider.submit(provider_request())

    assert result.status == "failed"
    assert result.error_code == "fal_configuration_error"
    assert not result.retryable
    assert client.submit_calls == []


def test_image_and_character_jobs_freeze_fal_model_selection(
    client: TestClient,
    headers: dict[str, str],
    project: dict[str, Any],
    episode: dict[str, Any],
    png: bytes,
) -> None:
    character_asset = upload_asset(client, headers, project["id"], png)
    with app.state.session_factory() as db:
        character = Character(
            project_id=UUID(project["id"]),
            name="Mina",
            appearance="short black hair",
            clothing="violet jacket",
            reference_asset_id=UUID(character_asset["id"]),
        )
        db.add(character)
        db.commit()
        character_id = character.id
    scene = Scene(
        episode_id=UUID(episode["id"]),
        position=0,
        title="Mina on the roof",
        script={
            "visual_prompt": "Mina watches the city wake up.",
            "character_ids": [str(character_id)],
        },
    )
    with app.state.session_factory() as db:
        db.add(scene)
        db.commit()
        scene_id = scene.id
    user_id = UUID(client.get("/api/v1/auth/me", headers=headers).json()["id"])
    config = settings()
    with app.state.session_factory() as db:
        service = GenerationService(db, user_id, config)
        scene_job = service.create_scene_image_job(scene_id, "fal-reference-scene")
        reference_job = service.create_character_reference_job(
            character_id, "fal-new-character-reference"
        )

        assert scene_job.provider == "fal"
        assert scene_job.provider_model == config.fal_reference_image_model
        assert reference_job.provider == "fal"
        assert reference_job.provider_model == config.fal_image_model


def test_fal_ambiguous_submit_timeout_is_never_retried_by_worker() -> None:
    class TimeoutClient(FakeFalClient):
        def submit(self, model: str, arguments: dict[str, Any]) -> str:
            self.submit_calls.append((model, arguments))
            raise httpx.TimeoutException(
                "private detail", request=httpx.Request("POST", "https://queue.fal.run")
            )

    client = TimeoutClient()
    provider = FalProvider(settings(), client=client)
    result = provider.submit(provider_request())

    assert result.status == "failed"
    assert result.error_code == "fal_submit_outcome_unknown"
    assert result.retryable is False
    assert len(client.submit_calls) == 1


def test_fal_poll_timeout_is_classified_as_retryable_timeout() -> None:
    class TimeoutStatusClient(FakeFalClient):
        def status(self, model: str, request_id: str) -> object:
            raise httpx.ReadTimeout(
                "private detail",
                request=httpx.Request("GET", "https://queue.fal.run/requests/fal-request-123"),
            )

    provider = FalProvider(settings(), client=TimeoutStatusClient())
    request = provider_request()

    result = provider.poll(
        "fal-request-123", request, {"model": "fal-ai/flux-2-pro", "poll_count": 1}
    )

    assert result.status == "failed"
    assert result.error_code == "fal_timeout"
    assert result.retryable is True
    assert result.error_message == "fal.ai could not be reached reliably."


def test_fal_cancel_uses_saved_model_and_skips_completed_tasks() -> None:
    client = FakeFalClient()
    client.statuses = [Queued(position=0), completed()]
    provider = FalProvider(settings(), client=client)

    provider.cancel("fal-request-123", "fal-ai/flux-pulid")
    provider.cancel("fal-request-123", "fal-ai/flux-2-pro")

    assert client.cancel_calls == [("fal-ai/flux-pulid", "fal-request-123")]


def test_fal_rejects_output_urls_outside_provider_hosts() -> None:
    provider = FalProvider(settings(), client=FakeFalClient())
    request = provider_request()
    result = SimpleNamespace(
        provider_task_id="fal-request-123",
        state={
            "model": "fal-ai/flux-2-pro",
            "result": {
                "images": [
                    {
                        "url": "http://127.0.0.1/private.png",
                        "content_type": "image/png",
                    }
                ]
            },
        },
    )

    with pytest.raises(ApplicationError, match="unsafe or invalid"):
        provider.normalize_result(result, request)  # type: ignore[arg-type]


def test_fal_scene_job_survives_storage_retry_without_resubmitting(
    client: TestClient,
    headers: dict[str, str],
    project: dict[str, Any],
    episode: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = Scene(
        episode_id=UUID(episode["id"]),
        position=0,
        title="Dawn rooftop",
        script={"visual_prompt": "Moonlit rooftops at dawn", "narration": "A courier pauses."},
    )
    with app.state.session_factory() as db:
        db.add(scene)
        db.commit()
        scene_id = scene.id
    user_id = UUID(client.get("/api/v1/auth/me", headers=headers).json()["id"])
    config = settings()
    with app.state.session_factory() as db:
        job = GenerationService(db, user_id, config).create_scene_image_job(scene_id, "fal-e2e-key")
        job_id = job.id
        assert job.provider == "fal"
        assert job.provider_model == "fal-ai/flux-2-pro"

    fal_client = FakeFalClient()
    fal_client.statuses = [completed()]
    fal_client.result_value = {
        "images": [
            {
                "url": "https://storage.googleapis.com/fal-output/generated.png",
                "content_type": "image/png",
            }
        ]
    }
    provider = FalProvider(config, client=fal_client)
    monkeypatch.setattr(
        provider,
        "download_artifact",
        lambda url, limit: (png_bytes(), "image/png"),
    )
    storage = FailOnceStorage()
    worker = DatabaseWorker(
        app.state.session_factory,
        config,
        ProviderRegistry([provider]),
        "fal-worker-test",
    )
    worker.processor = JobProcessor(
        app.state.session_factory,
        config,
        ProviderRegistry([provider]),
        storage,
    )

    assert worker.run_once()
    with app.state.session_factory() as db:
        stored = db.get(GenerationJob, job_id)
        assert stored is not None
        assert stored.status == "provider_pending"
        assert stored.provider_task_id == "fal-request-123"
        assert stored.provider_model == "fal-ai/flux-2-pro"
        stored.next_poll_at = utcnow() - timedelta(seconds=1)
        db.commit()

    assert worker.run_once()
    with app.state.session_factory() as db:
        stored = db.get(GenerationJob, job_id)
        assert stored is not None
        assert stored.status == "saving"
        assert stored.provider_output["artifacts"][0]["source_url"].startswith("https://")
        stored.next_poll_at = utcnow() - timedelta(seconds=1)
        db.commit()

    assert worker.run_once()
    assert len(fal_client.submit_calls) == 1
    assert len(fal_client.cancel_calls) == 0
    with app.state.session_factory() as db:
        stored = db.get(GenerationJob, job_id)
        saved_scene = db.get(Scene, scene_id)
        assert stored is not None and saved_scene is not None
        assert stored.status == "succeeded"
        assert stored.provider_output == {}
        assert saved_scene.image_asset_id is not None
        asset = db.get(Asset, saved_scene.image_asset_id)
        assert asset is not None
        assert asset.provider == "fal"
        assert asset.generation_job_id == job_id
        assert storage.read(asset.storage_key) == png_bytes()


@pytest.mark.skipif(
    os.getenv("RUN_FAL_INTEGRATION_TESTS", "").lower() != "true",
    reason="Set RUN_FAL_INTEGRATION_TESTS=true to opt in to one paid fal.ai image request.",
)
def test_fal_opt_in_live_image_smoke() -> None:
    key = os.getenv("FAL_KEY")
    if not key:
        pytest.skip("FAL_KEY is not set")
    config = settings(fal_key=key)
    provider = FalProvider(config)
    request = ProviderRequest(
        job_id=uuid4(),
        kind="image",
        action="scene",
        provider_model=config.fal_image_model,
        input_data={"scene_id": str(uuid4()), "prompt": "A small blue studio test image."},
        attempt=0,
        idempotency_key="fal-opt-in-smoke",
    )
    submitted = provider.submit(request)
    assert submitted.status == "pending", submitted.error_code
    result = None
    state = submitted.state
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        result = provider.poll(submitted.provider_task_id, request, state)
        state = result.state
        if result.status != "pending":
            break
        time.sleep(result.poll_after_seconds or config.worker_provider_poll_seconds)
    assert result is not None and result.status == "completed", (
        result.error_code if result else "fal.ai smoke timed out"
    )
    normalized = provider.normalize_result(result, request)
    assert normalized.kind == "image"
    assert len(normalized.artifacts) == 1
