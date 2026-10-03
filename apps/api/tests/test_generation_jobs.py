from typing import Any
from uuid import UUID

import pytest
from conftest import register
from fastapi.testclient import TestClient

from app.config import Settings
from app.errors import ApplicationError
from app.main import app
from app.models import GenerationJob
from app.services import GenerationCategory, GenerationService


def create_job(
    client: TestClient,
    headers: dict[str, str],
    project: dict[str, Any],
    *,
    category: GenerationCategory = "story",
    action: str = "outline",
    idempotency_key: str | None = None,
) -> str:
    user_id = UUID(client.get("/api/v1/auth/me", headers=headers).json()["id"])
    settings = Settings(_env_file=None)
    with app.state.session_factory() as db:
        service = GenerationService(db, user_id, settings)
        job = service.create_job(
            UUID(project["id"]),
            category,
            action,
            {"prompt": "A lighthouse in winter"},
            idempotency_key,
        )
        return str(job.id)


def test_job_detail_is_owner_scoped_and_hides_provider_output(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    job_id = create_job(client, headers, project)

    response = client.get(f"/api/v1/jobs/{job_id}", headers=headers)
    assert response.status_code == 200, response.text
    job = response.json()
    assert job["id"] == job_id
    assert job["job_type"] == "story:outline"
    assert job["status"] == "queued"
    assert job["input"] == {"prompt": "A lighthouse in winter"}
    assert job["output"] == {}
    assert job["retry_count"] == 0
    assert job["updated_at"]
    assert "provider" not in job
    assert "provider_model" not in job
    assert "provider_task_id" not in job
    assert "provider_metadata" not in job["output"]
    assert "provider_output" not in job
    assert "lease_owner" not in job

    other = register(client, "job-reader@example.com")
    assert client.get(f"/api/v1/jobs/{job_id}", headers=other).status_code == 404
    assert client.post(f"/api/v1/jobs/{job_id}/cancel", headers=other).status_code == 404


def test_job_details_hide_provider_identifiers_and_error_diagnostics(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    job_id = create_job(client, headers, project)
    with app.state.session_factory() as db:
        job = db.get(GenerationJob, UUID(job_id))
        assert job is not None
        job.provider = "runway"
        job.provider_model = "gen4_turbo"
        job.provider_task_id = "runway-secret-task"
        job.input = {
            "scene_id": "scene-123",
            "model": "gen4_turbo",
            "provider_task_id": "runway-secret-task",
        }
        job.output = {"asset_id": "asset-123", "provider_metadata": {"provider": "runway"}}
        job.error_code = "runway_authentication_error"
        job.error_message = "Runway rejected this internal-secret value."
        db.commit()

    detail = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
    assert "provider" not in detail
    assert "provider_model" not in detail
    assert "provider_task_id" not in detail
    assert detail["error_code"] == "provider_error"
    assert detail["error_message"] == "The AI service could not complete this generation."
    assert detail["input"] == {"scene_id": "scene-123"}
    assert detail["output"] == {"asset_id": "asset-123"}
    assert "runway" not in str(detail).lower()
    assert "gen4" not in str(detail).lower()
    assert "secret" not in str(detail).lower()


def test_job_creation_is_idempotent_and_conflicts_are_rejected(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    user_id = UUID(client.get("/api/v1/auth/me", headers=headers).json()["id"])
    project_id = UUID(project["id"])
    settings = Settings(_env_file=None)

    with app.state.session_factory() as db:
        service = GenerationService(db, user_id, settings)
        first = service.create_job(
            project_id,
            "image",
            "scene",
            {"scene": 1},
            "scene-image-1",
        )
        duplicate = service.create_job(
            project_id,
            "image",
            "scene",
            {"scene": 1},
            " scene-image-1 ",
        )
        assert duplicate.id == first.id

        with pytest.raises(ApplicationError) as error:
            service.create_job(
                project_id,
                "image",
                "scene",
                {"scene": 2},
                "scene-image-1",
            )
        assert error.value.status == 409
        assert error.value.code == "idempotency_conflict"

    jobs = client.get("/api/v1/jobs", headers=headers).json()
    assert len(jobs) == 1


def test_job_status_transitions_and_cancel_endpoint(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    user_id = UUID(client.get("/api/v1/auth/me", headers=headers).json()["id"])
    project_id = UUID(project["id"])
    settings = Settings(_env_file=None)

    with app.state.session_factory() as db:
        service = GenerationService(db, user_id, settings)
        completed = service.create_job(project_id, "video", "panel", {"panel": 1})
        service.transition(completed.id, "running", progress=10)
        service.transition(completed.id, "provider_pending", progress=30)
        service.transition(completed.id, "saving", progress=80)
        service.transition(completed.id, "succeeded")
        assert completed.progress == 100
        assert completed.started_at is not None
        assert completed.completed_at is not None
        with pytest.raises(ApplicationError) as error:
            service.transition(completed.id, "running")
        assert error.value.code == "invalid_job_transition"

        pending = service.create_job(project_id, "character", "reference", {"character": 1})
        pending_id = str(pending.id)

    canceled = client.post(f"/api/v1/jobs/{pending_id}/cancel", headers=headers)
    assert canceled.status_code == 200, canceled.text
    assert canceled.json()["status"] == "canceled"
    assert canceled.json()["cancel_requested_at"]
    assert canceled.json()["completed_at"]
    assert client.post(f"/api/v1/jobs/{pending_id}/cancel", headers=headers).status_code == 200
    assert client.post(f"/api/v1/jobs/{completed.id}/cancel", headers=headers).status_code == 409


def test_character_and_video_jobs_share_existing_quota_buckets(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    create_job(client, headers, project, category="character", action="reference")
    create_job(client, headers, project, category="video", action="panel")

    quotas = client.get("/api/v1/quotas", headers=headers)
    assert quotas.status_code == 200
    assert quotas.json()["buckets"]["image"]["used"] == 1
    assert quotas.json()["buckets"]["motion"]["used"] == 1
