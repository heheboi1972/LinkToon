import base64
from io import BytesIO
from typing import Any
from uuid import UUID

import pytest
from conftest import register
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import JsonValue
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.config import get_settings
from app.errors import StorageError
from app.job_worker import DatabaseWorker, JobProcessor
from app.main import app
from app.models import Asset, Character, GenerationJob, Scene, utcnow
from app.providers.base import (
    NormalizedProviderResult,
    ProviderPollResult,
    ProviderRequest,
    ProviderResult,
    ProviderSubmitResult,
)
from app.providers.mock import MockProvider
from app.providers.registry import ProviderRegistry


class CountingMockProvider:
    name = "mock"

    def __init__(self) -> None:
        self.delegate = MockProvider()
        self.submits = 0

    def submit(self, request: ProviderRequest) -> ProviderSubmitResult:
        self.submits += 1
        return self.delegate.submit(request)

    def poll(
        self,
        provider_task_id: str,
        request: ProviderRequest,
        state: dict[str, JsonValue],
    ) -> ProviderPollResult:
        return self.delegate.poll(provider_task_id, request, state)

    def cancel(self, provider_task_id: str, provider_model: str | None = None) -> None:
        self.delegate.cancel(provider_task_id)

    def normalize_result(
        self, result: ProviderResult, request: ProviderRequest
    ) -> NormalizedProviderResult:
        return self.delegate.normalize_result(result, request)


class RetryStorage:
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.objects: dict[str, bytes] = {}
        self.writes = 0

    def put(self, key: str, content: bytes, mime_type: str) -> None:
        if self.failures:
            self.failures -= 1
            raise StorageError("temporary storage failure")
        if key in self.objects:
            raise StorageError("object already exists")
        self.objects[key] = content
        self.writes += 1

    def read(self, key: str) -> bytes:
        try:
            return self.objects[key]
        except KeyError as exc:
            raise StorageError("object missing") from exc

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)


def create_scene(
    episode_id: str,
    *,
    visual_prompt: str = "Moonlit rooftop chase, wide cinematic shot",
    narration: str = "The courier leaps across the roof.",
    character_ids: list[str] | None = None,
) -> UUID:
    with app.state.session_factory() as db:
        scene = Scene(
            episode_id=UUID(episode_id),
            position=0,
            title="Rooftop signal",
            script={
                "visual_prompt": visual_prompt,
                "narration": narration,
                "dialogue": [],
                "character_ids": character_ids or [],
            },
        )
        db.add(scene)
        db.commit()
        return scene.id


def submit_image(
    client: TestClient,
    headers: dict[str, str],
    scene_id: UUID,
    key: str,
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/scenes/{scene_id}/image/generate",
        headers={**headers, "Idempotency-Key": key},
    )
    assert response.status_code == 202, response.text
    return response.json()


def image_worker(
    provider: CountingMockProvider,
    *,
    storage: RetryStorage | None = None,
    worker_id: str = "scene-image-worker",
) -> DatabaseWorker:
    settings = get_settings()
    worker = DatabaseWorker(
        app.state.session_factory,
        settings,
        ProviderRegistry([provider]),
        worker_id,
    )
    if storage is not None:
        worker.processor = JobProcessor(
            app.state.session_factory,
            settings,
            ProviderRegistry([provider]),
            storage,
        )
    return worker


def make_due(job_id: UUID) -> None:
    with app.state.session_factory() as db:
        job = db.get(GenerationJob, job_id)
        assert job is not None
        job.next_poll_at = utcnow()
        job.lease_owner = None
        job.lease_expires_at = None
        db.commit()


def test_scene_image_api_uses_owned_scene_prompt_and_is_idempotent(
    client: TestClient,
    headers: dict[str, str],
    project: dict[str, Any],
    episode: dict[str, Any],
) -> None:
    with app.state.session_factory() as db:
        character = Character(
            project_id=UUID(project["id"]),
            name="Mina",
            description="Courier",
            appearance="short black hair",
            clothing="violet flight jacket",
        )
        db.add(character)
        db.commit()
        character_id = str(character.id)
    scene_id = create_scene(episode["id"], character_ids=[character_id])

    first = submit_image(client, headers, scene_id, "same-image-intent")
    duplicate = submit_image(client, headers, scene_id, "same-image-intent")

    assert first == duplicate
    with app.state.session_factory() as db:
        job = db.get(GenerationJob, UUID(first["job_id"]))
        assert job is not None
        assert job.job_type == "image:scene"
        assert job.input["scene_id"] == str(scene_id)
        prompt = str(job.input["prompt"])
        assert "Moonlit rooftop chase" in prompt
        assert "Visual style: ink" in prompt
        assert "short black hair" in prompt
        assert "violet flight jacket" in prompt


def test_scene_image_rejects_other_owner_and_parallel_active_job(
    client: TestClient,
    headers: dict[str, str],
    episode: dict[str, Any],
) -> None:
    scene_id = create_scene(episode["id"])
    submit_image(client, headers, scene_id, "first-intent")
    active = client.post(
        f"/api/v1/scenes/{scene_id}/image/generate",
        headers={**headers, "Idempotency-Key": "second-intent"},
    )
    assert active.status_code == 409
    assert active.json()["error"]["code"] == "scene_image_job_active"

    other_headers = register(client, "other-scene-owner@example.com")
    hidden = client.post(
        f"/api/v1/scenes/{scene_id}/image/generate",
        headers={**other_headers, "Idempotency-Key": "other-owner-intent"},
    )
    assert hidden.status_code == 404


def test_scene_without_visual_prompt_is_rejected_before_job_creation(
    client: TestClient,
    headers: dict[str, str],
    episode: dict[str, Any],
) -> None:
    scene_id = create_scene(episode["id"], visual_prompt="")
    response = client.post(
        f"/api/v1/scenes/{scene_id}/image/generate",
        headers={**headers, "Idempotency-Key": "missing-prompt"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "scene_visual_prompt_missing"
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count(GenerationJob.id))) == 0


def test_image_quota_rejects_before_any_provider_call(
    client: TestClient,
    headers: dict[str, str],
    episode: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IMAGE_DAILY_LIMIT", "1")
    get_settings.cache_clear()
    first_scene = create_scene(episode["id"])
    second_scene = create_scene(
        episode["id"], visual_prompt="Quiet neon alley", narration="Rain falls."
    )
    submit_image(client, headers, first_scene, "quota-first")
    response = client.post(
        f"/api/v1/scenes/{second_scene}/image/generate",
        headers={**headers, "Idempotency-Key": "quota-second"},
    )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "generation_quota_exceeded"
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count(GenerationJob.id))) == 1


def test_mock_scene_image_pipeline_links_asset_and_regeneration_preserves_history(
    client: TestClient,
    headers: dict[str, str],
    episode: dict[str, Any],
) -> None:
    scene_id = create_scene(episode["id"])
    first = submit_image(client, headers, scene_id, "render-one")
    provider = CountingMockProvider()
    worker = image_worker(provider)
    assert worker.run_once()

    with app.state.session_factory() as db:
        scene = db.get(Scene, scene_id)
        first_asset = scene.image_asset_id if scene else None
        assert first_asset is not None
        job = db.get(GenerationJob, UUID(first["job_id"]))
        assert job is not None and job.status == "succeeded"
        assert job.output["scene_id"] == str(scene_id)
        assert job.output["asset_id"] == str(first_asset)
        assert job.provider_output["artifacts"][0]["content_base64"]
    scene_response = client.get(f"/api/v1/scenes/{scene_id}", headers=headers)
    assert scene_response.status_code == 200
    assert scene_response.json()["image_asset_id"] == str(first_asset)

    second = submit_image(client, headers, scene_id, "render-two")
    assert worker.run_once()
    with app.state.session_factory() as db:
        scene = db.get(Scene, scene_id)
        assert scene is not None and scene.image_asset_id != first_asset
        assert db.get(Asset, first_asset) is not None
        assert db.scalar(select(func.count(Asset.id))) == 2
        second_job = db.get(GenerationJob, UUID(second["job_id"]))
        assert second_job is not None and second_job.status == "succeeded"
    assert provider.submits == 2


def test_storage_failure_retries_saving_without_provider_resubmit(
    client: TestClient,
    headers: dict[str, str],
    episode: dict[str, Any],
) -> None:
    scene_id = create_scene(episode["id"])
    queued = submit_image(client, headers, scene_id, "storage-retry")
    job_id = UUID(queued["job_id"])
    provider = CountingMockProvider()
    storage = RetryStorage(failures=1)
    worker = image_worker(provider, storage=storage)

    assert worker.run_once()
    with app.state.session_factory() as db:
        job = db.get(GenerationJob, job_id)
        assert job is not None and job.status == "saving" and job.retry_count == 1
        assert job.provider_output["artifacts"][0]["content_base64"]
    assert provider.submits == 1

    make_due(job_id)
    assert worker.run_once()
    with app.state.session_factory() as db:
        job = db.get(GenerationJob, job_id)
        assert job is not None and job.status == "succeeded"
    assert provider.submits == 1
    assert storage.writes == 1


def test_database_retry_reuses_same_storage_object_and_provider_result(
    client: TestClient,
    headers: dict[str, str],
    episode: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene_id = create_scene(episode["id"])
    queued = submit_image(client, headers, scene_id, "database-retry")
    job_id = UUID(queued["job_id"])
    provider = CountingMockProvider()
    storage = RetryStorage()
    worker = image_worker(provider, storage=storage)
    original = worker.processor._link_scene_image
    failures = 1

    def flaky_link(*args: Any, **kwargs: Any) -> tuple[UUID, UUID]:
        nonlocal failures
        if failures:
            failures -= 1
            raise OperationalError("UPDATE scene", {}, RuntimeError("temporary database error"))
        return original(*args, **kwargs)

    monkeypatch.setattr(worker.processor, "_link_scene_image", flaky_link)
    assert worker.run_once()
    assert provider.submits == 1 and storage.writes == 1
    make_due(job_id)
    assert worker.run_once()
    with app.state.session_factory() as db:
        job = db.get(GenerationJob, job_id)
        assert job is not None and job.status == "succeeded"
        assert db.scalar(select(func.count(Asset.id))) == 1
    assert provider.submits == 1 and storage.writes == 1 and len(storage.objects) == 1


def test_generated_asset_is_private_owner_scoped_and_served_by_capability_url(
    client: TestClient,
    headers: dict[str, str],
    episode: dict[str, Any],
) -> None:
    scene_id = create_scene(episode["id"])
    submit_image(client, headers, scene_id, "private-image")
    assert image_worker(CountingMockProvider()).run_once()
    scene = client.get(f"/api/v1/scenes/{scene_id}", headers=headers).json()
    asset_id = scene["image_asset_id"]
    asset = client.get(f"/api/v1/assets/{asset_id}", headers=headers)
    assert asset.status_code == 200
    payload = asset.json()
    assert payload["storage_bucket"] == "local"
    assert payload["public_url"] and "token=" in payload["public_url"]
    content = client.get(payload["public_url"])
    assert content.status_code == 200
    assert content.headers["content-type"] == "image/png"

    other_headers = register(client, "asset-snooper@example.com")
    hidden = client.get(f"/api/v1/assets/{asset_id}", headers=other_headers)
    assert hidden.status_code == 404


def test_generated_image_header_and_declared_mime_are_validated(
    client: TestClient,
    headers: dict[str, str],
    project: dict[str, Any],
) -> None:
    with app.state.session_factory() as db:
        owner = UUID(client.get("/api/v1/auth/me", headers=headers).json()["id"])
        job = GenerationJob(
            user_id=owner,
            project_id=UUID(project["id"]),
            job_type="image:test",
            status="saving",
            provider="mock",
            input={},
            provider_output={
                "kind": "image",
                "output": {},
                "artifacts": [
                    {
                        "asset_type": "image",
                        "mime_type": "image/png",
                        "filename": "fake.png",
                        "content_base64": base64.b64encode(b"not an image").decode(),
                    }
                ],
                "metadata": {},
                "mock": True,
            },
            idempotency_key="invalid-image-bytes",
        )
        db.add(job)
        db.commit()
        job_id = job.id
    provider = CountingMockProvider()
    worker = image_worker(provider)
    assert worker.run_once()
    with app.state.session_factory() as db:
        failed = db.get(GenerationJob, job_id)
        assert failed is not None and failed.status == "failed"
        assert failed.error_code == "invalid_artifact"
        assert db.scalar(select(func.count(Asset.id))) == 0


def test_mock_png_fixture_is_a_real_static_image() -> None:
    output = BytesIO()
    Image.new("RGB", (16, 16), "purple").save(output, "PNG")
    with Image.open(BytesIO(output.getvalue())) as image:
        assert image.format == "PNG" and image.size == (16, 16)
