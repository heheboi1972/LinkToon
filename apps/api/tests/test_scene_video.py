from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from conftest import register, upload_asset
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings, get_settings
from app.errors import ApplicationError, StorageError
from app.job_worker import DatabaseWorker, JobProcessor
from app.main import app
from app.models import Asset, GenerationJob, Scene
from app.providers.mock import MockProvider
from app.providers.registry import ProviderRegistry
from app.providers.runway import RunwayProvider
from app.services import GenerationService


def create_scene_with_image(episode_id: str, asset_id: str | None = None) -> UUID:
    with app.state.session_factory() as db:
        scene = Scene(
            episode_id=UUID(episode_id),
            position=0,
            title="Moonlit rooftop",
            image_asset_id=UUID(asset_id) if asset_id else None,
            script={
                "narration": "Mina looks up at the moon.",
                "visual_prompt": "A quiet moonlit rooftop, violet light.",
                "character_ids": [],
            },
        )
        db.add(scene)
        db.commit()
        return scene.id


def request_video(client: TestClient, headers: dict[str, str], scene_id: UUID, key: str):
    return client.post(
        f"/api/v1/scenes/{scene_id}/video/generate",
        headers={**headers, "Idempotency-Key": key},
    )


def make_due(job_id: UUID) -> None:
    with app.state.session_factory() as db:
        job = db.get(GenerationJob, job_id)
        assert job is not None
        job.next_poll_at = job.updated_at
        job.lease_owner = None
        job.lease_expires_at = None
        db.commit()


class FakeRunwaySDK:
    def __init__(self) -> None:
        self.create_calls: list[dict[str, Any]] = []
        self.poll_calls: list[str] = []
        self.delete_calls: list[str] = []
        self.status = "SUCCEEDED"
        self.image_to_video = SimpleNamespace(create=self.create)
        self.tasks = SimpleNamespace(retrieve=self.retrieve, delete=self.delete)

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.create_calls.append(kwargs)
        return SimpleNamespace(id="durable-runway-task")

    def retrieve(self, task_id: str) -> SimpleNamespace:
        self.poll_calls.append(task_id)
        return SimpleNamespace(
            status=self.status,
            output=["https://cdn.runwayml.com/result.mp4?temporary=private"],
        )

    def delete(self, task_id: str) -> None:
        self.delete_calls.append(task_id)


class FlakyStorage:
    def __init__(self, failures: int = 1) -> None:
        self.failures = failures
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, content: bytes, mime_type: str) -> None:
        if self.failures:
            self.failures -= 1
            raise StorageError("temporary object store failure")
        if key in self.objects:
            raise StorageError("object already exists")
        self.objects[key] = content

    def read(self, key: str) -> bytes:
        if key not in self.objects:
            raise StorageError("object missing")
        return self.objects[key]

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)


def seed_source_image(storage: FlakyStorage, job_id: UUID, content: bytes) -> None:
    with app.state.session_factory() as db:
        job = db.get(GenerationJob, job_id)
        assert job is not None
        image = db.get(Asset, UUID(job.input["image_asset_id"]))
        assert image is not None
        storage.objects[image.storage_key] = content


class DownloadingRunwayProvider(RunwayProvider):
    def __init__(self, settings: Settings, client: FakeRunwaySDK, *, expired: bool = False) -> None:
        super().__init__(settings, client)
        self.downloads = 0
        self.expired = expired
        self.video_bytes = (
            Path(__file__).parents[1] / "app" / "providers" / "fixtures" / "mock-motion.mp4"
        ).read_bytes()

    def download_artifact(self, source_url: str, max_bytes: int) -> tuple[bytes, str]:
        self.downloads += 1
        if self.expired:
            raise ApplicationError(
                "Runway's temporary video has expired", "runway_output_expired", 410
            )
        assert source_url.startswith("https://cdn.runwayml.com/")
        assert len(self.video_bytes) <= max_bytes
        return self.video_bytes, "video/mp4"


def create_runway_job(
    client: TestClient,
    headers: dict[str, str],
    project: dict[str, Any],
    episode: dict[str, Any],
    png: bytes,
    settings: Settings,
) -> UUID:
    image = upload_asset(client, headers, project["id"], png)
    scene_id = create_scene_with_image(episode["id"], image["id"])
    owner_id = UUID(client.get("/api/v1/auth/me", headers=headers).json()["id"])
    with app.state.session_factory() as db:
        job = GenerationService(db, owner_id, settings).create_scene_video_job(
            scene_id, "runway-integration-test"
        )
        return job.id


def test_video_generation_requires_ready_owned_scene_image(
    client: TestClient,
    headers: dict[str, str],
    project: dict[str, Any],
    episode: dict[str, Any],
    png: bytes,
) -> None:
    scene_id = create_scene_with_image(episode["id"])
    missing = request_video(client, headers, scene_id, "motion-no-image")
    assert missing.status_code == 409
    assert missing.json()["error"]["code"] == "scene_image_required"

    image = upload_asset(client, headers, project["id"], png)
    scene_id = create_scene_with_image(episode["id"], image["id"])
    other_project = client.post(
        "/api/v1/projects", headers=headers, json={"title": "Other", "visual_style": "ink"}
    ).json()
    other_image = upload_asset(client, headers, other_project["id"], png)
    with app.state.session_factory() as db:
        scene = db.get(Scene, scene_id)
        assert scene is not None
        scene.image_asset_id = UUID(other_image["id"])
        db.commit()
    invalid = request_video(client, headers, scene_id, "motion-wrong-project-image")
    assert invalid.status_code == 409
    assert invalid.json()["error"]["code"] == "scene_image_required"

    scene_other_owner = create_scene_with_image(episode["id"])
    other_user = register(client, "other-artist@example.com")
    denied = request_video(client, other_user, scene_other_owner, "motion-not-owned")
    assert denied.status_code == 404


def test_scene_video_job_is_idempotent_and_blocks_active_duplicate(
    client: TestClient,
    headers: dict[str, str],
    project: dict[str, Any],
    episode: dict[str, Any],
    png: bytes,
) -> None:
    image = upload_asset(client, headers, project["id"], png)
    scene_id = create_scene_with_image(episode["id"], image["id"])

    first = request_video(client, headers, scene_id, "motion-intent-1")
    again = request_video(client, headers, scene_id, "motion-intent-1")
    duplicate = request_video(client, headers, scene_id, "motion-intent-2")

    assert first.status_code == again.status_code == 202
    assert first.json()["job_id"] == again.json()["job_id"]
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "scene_video_job_active"


def test_motion_usage_limit_rejects_before_creating_another_job(
    client: TestClient,
    headers: dict[str, str],
    project: dict[str, Any],
    episode: dict[str, Any],
    png: bytes,
) -> None:
    image = upload_asset(client, headers, project["id"], png)
    first_scene = create_scene_with_image(episode["id"], image["id"])
    second_scene = create_scene_with_image(episode["id"], image["id"])
    owner_id = UUID(client.get("/api/v1/auth/me", headers=headers).json()["id"])
    settings = get_settings().model_copy(update={"motion_daily_limit": 1})

    with app.state.session_factory() as db:
        service = GenerationService(db, owner_id, settings)
        service.create_scene_video_job(first_scene, "quota-first")
        with pytest.raises(ApplicationError) as error:
            service.create_scene_video_job(second_scene, "quota-second")
    assert error.value.status == 429
    assert error.value.code == "generation_quota_exceeded"


def test_mock_scene_video_pipeline_saves_private_mp4_supports_range_and_preserves_history(
    client: TestClient,
    headers: dict[str, str],
    project: dict[str, Any],
    episode: dict[str, Any],
    png: bytes,
) -> None:
    image = upload_asset(client, headers, project["id"], png)
    scene_id = create_scene_with_image(episode["id"], image["id"])
    accepted = request_video(client, headers, scene_id, "motion-e2e-1")
    assert accepted.status_code == 202, accepted.text
    job_id = UUID(accepted.json()["job_id"])

    worker = DatabaseWorker(
        app.state.session_factory,
        get_settings(),
        ProviderRegistry([MockProvider()]),
        "mock-video-worker",
    )
    assert worker.run_once()
    result = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
    assert result["status"] == "succeeded"
    video_id = UUID(result["output"]["video_asset_id"])
    assert video_id == uuid5(NAMESPACE_URL, f"linktoon:asset:{job_id}:0")
    scene = client.get(f"/api/v1/scenes/{scene_id}", headers=headers).json()
    assert scene["video_asset_id"] == str(video_id)
    video = client.get(f"/api/v1/assets/{video_id}", headers=headers).json()
    assert video["asset_type"] == "video"
    assert video["mime_type"] == "video/mp4"
    assert video["metadata"]["mock_provider"] is True
    assert "provider" not in video and "provider_task_id" not in video
    assert "provider" not in video["metadata"]
    assert "model" not in video["metadata"]
    assert video["file_size"] > 0
    response = client.get(video["public_url"], headers={"Range": "bytes=0-15"})
    assert response.status_code == 206
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-range"] == f"bytes 0-15/{video['file_size']}"
    assert len(response.content) == 16

    next_job = request_video(client, headers, scene_id, "motion-e2e-2")
    assert next_job.status_code == 202
    assert worker.run_once()
    new_scene = client.get(f"/api/v1/scenes/{scene_id}", headers=headers).json()
    assert new_scene["video_asset_id"] != str(video_id)
    with app.state.session_factory() as db:
        old_asset = db.scalar(select(Asset).where(Asset.id == video_id))
        assert old_asset is not None
        video_assets = list(
            db.scalars(
                select(Asset).where(
                    Asset.project_id == UUID(project["id"]), Asset.asset_type == "video"
                )
            )
        )
    assert len(video_assets) == 2


def test_mock_video_asset_cannot_be_deleted_while_linked(
    client: TestClient,
    headers: dict[str, str],
    project: dict[str, Any],
    episode: dict[str, Any],
    png: bytes,
) -> None:
    image = upload_asset(client, headers, project["id"], png)
    scene_id = create_scene_with_image(episode["id"], image["id"])
    accepted = request_video(client, headers, scene_id, "motion-asset-protect")
    worker = DatabaseWorker(
        app.state.session_factory,
        get_settings(),
        ProviderRegistry([MockProvider()]),
        "mock-video-worker",
    )
    assert worker.run_once()
    result = client.get(f"/api/v1/jobs/{accepted.json()['job_id']}", headers=headers).json()
    deletion = client.delete(
        f"/api/v1/assets/{result['output']['video_asset_id']}", headers=headers
    )
    assert deletion.status_code == 409
    assert deletion.json()["error"]["code"] == "asset_in_use"


def test_runway_worker_restart_and_storage_recovery_do_not_resubmit(
    client: TestClient,
    headers: dict[str, str],
    project: dict[str, Any],
    episode: dict[str, Any],
    png: bytes,
) -> None:
    settings = Settings(
        _env_file=None,
        local_auth_secret="test-secret-" * 8,
        mock_ai=False,
        runwayml_api_secret="worker-secret",
        worker_provider_poll_seconds=0.1,
        worker_retry_base_seconds=0.1,
        worker_lease_seconds=10,
    )
    job_id = create_runway_job(client, headers, project, episode, png, settings)
    client_sdk = FakeRunwaySDK()
    provider = DownloadingRunwayProvider(settings, client_sdk)
    registry = ProviderRegistry([provider])
    storage = FlakyStorage()
    seed_source_image(storage, job_id, png)

    first_worker = DatabaseWorker(app.state.session_factory, settings, registry, "runway-worker-1")
    first_worker.processor = JobProcessor(app.state.session_factory, settings, registry, storage)
    assert first_worker.run_once()
    with app.state.session_factory() as db:
        job = db.get(GenerationJob, job_id)
        assert job is not None
        assert job.status == "provider_pending", f"{job.error_code}: {job.error_message}"
        assert job.provider_task_id == "durable-runway-task"
        assert job.provider_output["state"]["model"] == "gen4_turbo"
    assert client_sdk.create_calls[0]["prompt_image"].startswith("data:image/png;base64,")

    make_due(job_id)
    restarted_worker = DatabaseWorker(
        app.state.session_factory, settings, registry, "runway-worker-restarted"
    )
    restarted_worker.processor = JobProcessor(
        app.state.session_factory, settings, registry, storage
    )
    assert restarted_worker.run_once()
    with app.state.session_factory() as db:
        job = db.get(GenerationJob, job_id)
        assert job is not None
        assert job.status == "saving"
        assert "temporary=private" in job.provider_output["artifacts"][0]["source_url"]

    make_due(job_id)
    retry_worker = DatabaseWorker(app.state.session_factory, settings, registry, "runway-worker-3")
    retry_worker.processor = JobProcessor(app.state.session_factory, settings, registry, storage)
    assert retry_worker.run_once()

    with app.state.session_factory() as db:
        job = db.get(GenerationJob, job_id)
        assert job is not None
        assert job.status == "succeeded"
        assert job.provider_task_id == "durable-runway-task"
        assert job.provider_output == {}
        assert "temporary=private" not in str(job.output)
        assert job.output["video_asset_id"]
    assert len(client_sdk.create_calls) == 1
    assert client_sdk.poll_calls == ["durable-runway-task"]
    assert provider.downloads == 2


def test_runway_provider_cancellation_maps_to_canceled_job(
    client: TestClient,
    headers: dict[str, str],
    project: dict[str, Any],
    episode: dict[str, Any],
    png: bytes,
) -> None:
    settings = Settings(
        _env_file=None,
        local_auth_secret="test-secret-" * 8,
        mock_ai=False,
        runwayml_api_secret="worker-secret",
        worker_provider_poll_seconds=0.1,
    )
    job_id = create_runway_job(client, headers, project, episode, png, settings)
    client_sdk = FakeRunwaySDK()
    provider = DownloadingRunwayProvider(settings, client_sdk)
    registry = ProviderRegistry([provider])
    storage = FlakyStorage(failures=0)
    seed_source_image(storage, job_id, png)
    worker = DatabaseWorker(app.state.session_factory, settings, registry, "runway-canceled-worker")
    worker.processor = JobProcessor(app.state.session_factory, settings, registry, storage)

    assert worker.run_once()
    client_sdk.status = "CANCELED"
    make_due(job_id)
    assert worker.run_once()

    with app.state.session_factory() as db:
        job = db.get(GenerationJob, job_id)
        assert job is not None
        assert job.status == "canceled"
        assert job.error_code == "runway_task_canceled"
        assert job.provider_output["state"]["runway_status"] == "CANCELED"
    assert len(client_sdk.create_calls) == 1
    assert client_sdk.poll_calls == ["durable-runway-task"]
    public_job = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
    assert "provider" not in public_job and "provider_task_id" not in public_job
    assert public_job["error_code"] == "provider_error"
    assert "runway" not in str(public_job).lower()


def test_expired_runway_output_fails_without_resubmitting_or_retaining_url(
    client: TestClient,
    headers: dict[str, str],
    project: dict[str, Any],
    episode: dict[str, Any],
    png: bytes,
) -> None:
    settings = Settings(
        _env_file=None,
        local_auth_secret="test-secret-" * 8,
        mock_ai=False,
        runwayml_api_secret="worker-secret",
        worker_provider_poll_seconds=0.1,
    )
    job_id = create_runway_job(client, headers, project, episode, png, settings)
    client_sdk = FakeRunwaySDK()
    provider = DownloadingRunwayProvider(settings, client_sdk, expired=True)
    registry = ProviderRegistry([provider])
    storage = FlakyStorage(failures=0)
    seed_source_image(storage, job_id, png)
    worker = DatabaseWorker(app.state.session_factory, settings, registry, "runway-expired-worker")
    worker.processor = JobProcessor(app.state.session_factory, settings, registry, storage)
    assert worker.run_once()
    make_due(job_id)
    assert worker.run_once()

    with app.state.session_factory() as db:
        job = db.get(GenerationJob, job_id)
        assert job is not None
        assert job.status == "failed"
        assert job.error_code == "runway_output_expired"
        assert job.provider_output == {}
    assert len(client_sdk.create_calls) == 1
    assert provider.downloads == 1
