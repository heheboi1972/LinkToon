import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from typing import Any
from uuid import UUID

import pytest
from conftest import upload_asset
from fastapi.testclient import TestClient
from pydantic import JsonValue
from sqlalchemy import func, select

from app.config import Settings
from app.errors import ApplicationError, StorageError
from app.job_worker import DatabaseWorker, JobProcessor, JobQueue
from app.main import app
from app.models import Asset, GenerationJob, Project, utcnow
from app.providers.base import (
    NormalizedProviderResult,
    ProviderPollResult,
    ProviderRequest,
    ProviderResult,
    ProviderSubmitResult,
)
from app.providers.mock import MockProvider
from app.providers.registry import ProviderRegistry, configured_registry
from app.services import GenerationCategory, GenerationService


class CountingProvider:
    name = "mock"

    def __init__(self) -> None:
        self.delegate = MockProvider()
        self.submits = 0
        self.polls = 0
        self.cancels = 0

    def submit(self, request: ProviderRequest) -> ProviderSubmitResult:
        self.submits += 1
        return self.delegate.submit(request)

    def poll(
        self,
        provider_task_id: str,
        request: ProviderRequest,
        state: dict[str, JsonValue],
    ) -> ProviderPollResult:
        self.polls += 1
        return self.delegate.poll(provider_task_id, request, state)

    def cancel(self, provider_task_id: str, provider_model: str | None = None) -> None:
        self.cancels += 1
        self.delegate.cancel(provider_task_id)

    def normalize_result(
        self, result: ProviderResult, request: ProviderRequest
    ) -> NormalizedProviderResult:
        return self.delegate.normalize_result(result, request)


class FlakyStorage:
    def __init__(self) -> None:
        self.failures = 1
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, content: bytes, mime_type: str) -> None:
        if self.failures:
            self.failures -= 1
            raise StorageError("Mock storage is temporarily unavailable")
        self.objects[key] = content

    def read(self, key: str) -> bytes:
        try:
            return self.objects[key]
        except KeyError as exc:
            raise StorageError("Mock storage object is missing") from exc

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)


def owner_id(client: TestClient, headers: dict[str, str]) -> UUID:
    return UUID(client.get("/api/v1/auth/me", headers=headers).json()["id"])


def worker_settings(**changes: object) -> Settings:
    return Settings(
        _env_file=None,
        worker_provider_poll_seconds=0.1,
        worker_retry_base_seconds=0.1,
        worker_lease_seconds=10,
        **changes,
    )


def create_job(
    client: TestClient,
    headers: dict[str, str],
    project: dict[str, Any],
    category: GenerationCategory,
    action: str,
    input_data: dict[str, Any],
    *,
    idempotency_key: str | None = None,
    settings: Settings | None = None,
) -> UUID:
    with app.state.session_factory() as db:
        job = GenerationService(
            db, owner_id(client, headers), settings or worker_settings()
        ).create_job(UUID(project["id"]), category, action, input_data, idempotency_key)
        return job.id


def job_state(job_id: UUID) -> dict[str, Any]:
    with app.state.session_factory() as db:
        job = db.get(GenerationJob, job_id)
        assert job is not None
        return {
            "status": job.status,
            "progress": job.progress,
            "provider": job.provider,
            "provider_task_id": job.provider_task_id,
            "provider_output": job.provider_output,
            "output": job.output,
            "retry_count": job.retry_count,
            "next_poll_at": job.next_poll_at,
            "lease_owner": job.lease_owner,
            "error_code": job.error_code,
            "error_message": job.error_message,
        }


def make_due(job_id: UUID) -> None:
    with app.state.session_factory() as db:
        job = db.get(GenerationJob, job_id)
        assert job is not None
        job.next_poll_at = utcnow() - timedelta(seconds=1)
        job.lease_owner = None
        job.lease_expires_at = None
        db.commit()


def build_worker(
    provider: CountingProvider,
    settings: Settings | None = None,
    *,
    worker_id: str = "worker-a",
) -> DatabaseWorker:
    return DatabaseWorker(
        app.state.session_factory,
        settings or worker_settings(),
        ProviderRegistry([provider]),
        worker_id,
    )


def test_job_claim_moves_to_running_and_prevents_second_claim(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    job_id = create_job(client, headers, project, "story", "outline", {"idea": "Moon"})
    queue = JobQueue(app.state.session_factory, worker_settings())

    claimed = queue.claim("worker-a")
    duplicate = queue.claim("worker-b")

    assert claimed is not None and claimed.id == job_id
    assert claimed.status == "running"
    assert duplicate is None
    state = job_state(job_id)
    assert state["status"] == "running"
    assert state["lease_owner"] == "worker-a"


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="PostgreSQL locking test")
def test_postgresql_concurrent_claim_returns_job_to_one_worker(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    job_id = create_job(client, headers, project, "story", "outline", {"idea": "Race"})
    barrier = Barrier(2)

    def claim(worker_id: str) -> UUID | None:
        barrier.wait()
        result = JobQueue(app.state.session_factory, worker_settings()).claim(worker_id)
        return result.id if result else None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ("worker-a", "worker-b")))
    assert results.count(job_id) == 1
    assert results.count(None) == 1


def test_mock_story_sync_pipeline_succeeds(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    job_id = create_job(
        client,
        headers,
        project,
        "story",
        "outline",
        {
            "idea": "A moonlit lighthouse",
            "genre": "fantasy",
            "theme": "courage",
            "characters": ["keeper"],
            "scene_count": 2,
        },
    )
    provider = CountingProvider()

    assert build_worker(provider).run_once()

    state = job_state(job_id)
    assert state["status"] == "succeeded"
    assert state["progress"] == 100
    assert state["output"]["mock"] is True
    assert len(state["output"]["scenes"]) == 2
    assert provider.submits == 1


def test_mock_image_creates_generated_asset(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    job_id = create_job(
        client, headers, project, "image", "scene", {"prompt": "A mock purple city"}
    )
    provider = CountingProvider()

    assert build_worker(provider).run_once()

    state = job_state(job_id)
    assert state["status"] == "succeeded"
    assert len(state["output"]["asset_ids"]) == 1
    with app.state.session_factory() as db:
        asset = db.scalar(select(Asset).where(Asset.generation_job_id == job_id))
        assert asset is not None
        assert asset.source == "generated"
        assert asset.provider == "mock"
        assert asset.mime_type == "image/png"
        assert asset.width == 16 and asset.height == 16


def test_async_mock_stays_pending_then_succeeds(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    job_id = create_job(
        client,
        headers,
        project,
        "story",
        "outline",
        {"idea": "Async", "mock_mode": "async", "mock_pending_polls": 1},
    )
    provider = CountingProvider()
    worker = build_worker(provider)

    assert worker.run_once()
    submitted = job_state(job_id)
    assert submitted["status"] == "provider_pending"
    assert submitted["provider_task_id"]
    first_poll_at = submitted["next_poll_at"]

    make_due(job_id)
    assert worker.run_once()
    pending = job_state(job_id)
    assert pending["status"] == "provider_pending"
    assert pending["next_poll_at"] > first_poll_at

    make_due(job_id)
    assert worker.run_once()
    assert job_state(job_id)["status"] == "succeeded"
    assert provider.submits == 1
    assert provider.polls == 2


def test_provider_failure_records_safe_error(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    job_id = create_job(client, headers, project, "story", "outline", {"mock_fail": True})

    assert build_worker(CountingProvider()).run_once()

    state = job_state(job_id)
    assert state["status"] == "failed"
    assert state["error_code"] == "mock_invalid_request"
    assert state["error_message"]


def test_stale_running_job_with_provider_task_is_polled_not_submitted(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    job_id = create_job(client, headers, project, "video", "panel", {})
    with app.state.session_factory() as db:
        job = db.get(GenerationJob, job_id)
        assert job is not None
        job.status = "running"
        job.provider_task_id = "existing-mock-task"
        job.provider_output = {"state": {"polls_remaining": 0}}
        job.lease_owner = "crashed-worker"
        job.lease_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    provider = CountingProvider()

    assert build_worker(provider, worker_id="recovery-worker").run_once()

    assert job_state(job_id)["status"] == "succeeded"
    assert provider.submits == 0
    assert provider.polls == 1


def test_stale_running_job_without_provider_task_is_safely_resubmitted(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    job_id = create_job(client, headers, project, "story", "outline", {"idea": "Recover"})
    with app.state.session_factory() as db:
        job = db.get(GenerationJob, job_id)
        assert job is not None
        job.status = "running"
        job.lease_owner = "crashed-before-submit"
        job.lease_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    provider = CountingProvider()

    assert build_worker(provider, worker_id="recovery-worker").run_once()

    assert job_state(job_id)["status"] == "succeeded"
    assert provider.submits == 1
    assert provider.polls == 0


def test_canceled_jobs_never_submit_and_pending_cancel_is_dispatched(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    user_id = owner_id(client, headers)
    queued_id = create_job(client, headers, project, "story", "outline", {})
    pending_id = create_job(client, headers, project, "video", "panel", {})
    settings = worker_settings()
    with app.state.session_factory() as db:
        pending = db.get(GenerationJob, pending_id)
        assert pending is not None
        pending.status = "provider_pending"
        pending.provider_task_id = "pending-task"
        pending.provider_output = {"state": {"polls_remaining": 1}}
        db.commit()
    with app.state.session_factory() as db:
        service = GenerationService(db, user_id, settings)
        service.cancel(queued_id)
        service.cancel(pending_id)
    provider = CountingProvider()
    worker = build_worker(provider, settings)

    assert worker.run_once()
    assert not worker.run_once()

    assert provider.submits == 0
    assert provider.polls == 0
    assert provider.cancels == 1
    assert job_state(queued_id)["status"] == "canceled"
    assert job_state(pending_id)["next_poll_at"] is None


def test_retry_limit_stops_temporary_failures(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    settings = worker_settings(worker_max_retries=1)
    job_id = create_job(
        client,
        headers,
        project,
        "story",
        "outline",
        {"mock_retryable_failures": 10},
        settings=settings,
    )
    provider = CountingProvider()
    worker = build_worker(provider, settings)

    assert worker.run_once()
    first = job_state(job_id)
    assert first["status"] == "queued"
    assert first["retry_count"] == 1

    make_due(job_id)
    assert worker.run_once()
    exhausted = job_state(job_id)
    assert exhausted["status"] == "failed"
    assert exhausted["retry_count"] == 1
    assert provider.submits == 2


def test_storage_retry_resumes_saving_without_provider_resubmit(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    settings = worker_settings(worker_max_retries=2)
    job_id = create_job(
        client, headers, project, "image", "scene", {"prompt": "Retry storage"}, settings=settings
    )
    provider = CountingProvider()
    worker = build_worker(provider, settings)
    worker.processor = JobProcessor(
        app.state.session_factory,
        settings,
        ProviderRegistry([provider]),
        FlakyStorage(),
    )

    assert worker.run_once()
    failed_save = job_state(job_id)
    assert failed_save["status"] == "saving"
    assert failed_save["retry_count"] == 1
    assert provider.submits == 1

    make_due(job_id)
    assert worker.run_once()
    assert job_state(job_id)["status"] == "succeeded"
    assert provider.submits == 1


def test_idempotent_request_is_processed_once(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    settings = worker_settings()
    first = create_job(
        client,
        headers,
        project,
        "story",
        "outline",
        {"idea": "Same"},
        idempotency_key="same-story",
        settings=settings,
    )
    duplicate = create_job(
        client,
        headers,
        project,
        "story",
        "outline",
        {"idea": "Same"},
        idempotency_key="same-story",
        settings=settings,
    )
    provider = CountingProvider()
    worker = build_worker(provider, settings)

    assert first == duplicate
    assert worker.run_once()
    assert not worker.run_once()
    assert provider.submits == 1


def test_worker_preserves_existing_project_and_uploaded_asset(
    client: TestClient,
    headers: dict[str, str],
    project: dict[str, Any],
    png: bytes,
) -> None:
    uploaded = upload_asset(client, headers, project["id"], png)
    job_id = create_job(client, headers, project, "story", "outline", {"idea": "Preserve"})

    assert build_worker(CountingProvider()).run_once()

    with app.state.session_factory() as db:
        saved_project = db.get(Project, UUID(project["id"]))
        saved_asset = db.get(Asset, UUID(uploaded["id"]))
        assert saved_project is not None and saved_project.title == "Moonlight"
        assert saved_asset is not None and saved_asset.upload_status == "ready"
        assert db.scalar(select(func.count(GenerationJob.id))) == 1
        assert db.get(GenerationJob, job_id) is not None


def test_mock_provider_is_not_registered_in_production() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        auth_mode="supabase",
        storage_provider="supabase",
        mock_ai=True,
        database_url="postgresql+psycopg://example:example@localhost/linktoon",
        api_public_url="https://api.example.com",
        cors_origins=["https://app.example.com"],
        supabase_url="https://example.supabase.co",
        supabase_anon_key="public-anon",
        supabase_service_role_key="server-only-secret",
    )

    with pytest.raises(ApplicationError, match="not configured"):
        configured_registry(settings).resolve("mock")
