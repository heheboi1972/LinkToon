from typing import Any
from uuid import UUID, uuid4

import pytest
from conftest import register, upload_asset
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.config import Settings
from app.errors import ApplicationError
from app.main import app
from app.models import ProjectBible
from app.services import GenerationService


def test_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/projects").status_code == 401
    headers = register(client)
    assert client.get("/api/v1/auth/me", headers=headers).json()["display_name"] == "Artist"
    result = client.post(
        "/api/v1/auth/login", json={"email": "ARTIST@example.com", "password": "long-password-123"}
    )
    assert result.status_code == 200
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "artist@example.com", "password": "wrong"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/signup",
            json={
                "email": "artist@example.com",
                "password": "long-password-123",
                "display_name": "Duplicate",
            },
        ).status_code
        == 409
    )
    assert (
        client.get("/api/v1/projects", headers={"Authorization": "Bearer invalid"}).status_code
        == 401
    )


def test_project_crud_and_atomic_bible(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    path = f"/api/v1/projects/{project['id']}"
    assert client.get("/api/v1/projects", headers=headers).json()[0]["id"] == project["id"]
    bible = client.get(f"{path}/bible", headers=headers).json()
    assert bible["visual_bible"]["preset"] == "ink"
    assert bible["prompt_rules"] == []
    assert (
        client.patch(path, headers=headers, json={"title": "New title", "status": "active"}).json()[
            "title"
        ]
        == "New title"
    )
    assert client.patch(path, headers=headers, json={"title": None}).status_code == 422
    assert client.patch(path, headers=headers, json={"owner_id": str(uuid4())}).status_code == 422
    assert client.delete(path, headers=headers).status_code == 204
    assert client.get(path, headers=headers).status_code == 404
    with app.state.session_factory() as db:
        assert db.scalar(select(ProjectBible)) is None


def test_episode_crud(
    client: TestClient, headers: dict[str, str], project: dict[str, Any], episode: dict[str, Any]
) -> None:
    path = f"/api/v1/episodes/{episode['id']}"
    assert episode["number"] == 1
    second = client.post(
        f"/api/v1/projects/{project['id']}/episodes", headers=headers, json={"title": "Next"}
    ).json()
    assert second["number"] == 2
    assert (
        len(client.get(f"/api/v1/projects/{project['id']}/episodes", headers=headers).json()) == 2
    )
    assert client.patch(path, headers=headers, json={"title": "Edited"}).json()["title"] == "Edited"
    assert client.get(path, headers=headers).json()["title"] == "Edited"
    assert client.patch(path, headers=headers, json={"status": "public"}).status_code == 422
    assert client.delete(path, headers=headers).status_code == 204
    assert client.get(path, headers=headers).status_code == 404


def test_twelve_panels_crud_and_image_link(
    client: TestClient,
    headers: dict[str, str],
    episode: dict[str, Any],
    project: dict[str, Any],
    png: bytes,
) -> None:
    path = f"/api/v1/episodes/{episode['id']}/panels"
    ids = []
    for index in range(12):
        response = client.post(path, headers=headers, json={"title": f"Panel {index}"})
        assert response.status_code == 201, response.text
        assert response.json()["position"] == index
        ids.append(response.json()["id"])
    assert len(client.get(path, headers=headers).json()) == 12
    asset = upload_asset(client, headers, project["id"], png)
    panel_path = f"/api/v1/panels/{ids[0]}"
    result = client.patch(
        panel_path, headers=headers, json={"image_asset_id": asset["id"], "dialogue": "Hello world"}
    )
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "static"
    assert client.get(panel_path, headers=headers).json()["dialogue"] == "Hello world"
    assert client.delete(f"/api/v1/assets/{asset['id']}", headers=headers).status_code == 409
    assert (
        client.patch(panel_path, headers=headers, json={"image_asset_id": None}).json()["status"]
        == "empty"
    )
    assert client.delete(panel_path, headers=headers).status_code == 204
    assert client.get(panel_path, headers=headers).status_code == 404
    assert len(client.get(path, headers=headers).json()) == 11


def test_ownership_on_nested_resources(
    client: TestClient, headers: dict[str, str], project: dict[str, Any], episode: dict[str, Any]
) -> None:
    panel = client.post(f"/api/v1/episodes/{episode['id']}/panels", headers=headers, json={}).json()
    other = register(client, "other@example.com")
    paths = [f"/projects/{project['id']}", f"/episodes/{episode['id']}", f"/panels/{panel['id']}"]
    for path in paths:
        assert client.get(f"/api/v1{path}", headers=other).status_code == 404
        assert (
            client.patch(f"/api/v1{path}", headers=other, json={"title": "Stolen"}).status_code
            == 404
        )
        assert client.delete(f"/api/v1{path}", headers=other).status_code == 404
    assert client.get("/api/v1/projects", headers=other).json() == []
    assert (
        client.post(
            f"/api/v1/projects/{project['id']}/episodes", headers=other, json={"title": "Stolen"}
        ).status_code
        == 404
    )
    assert (
        client.post(f"/api/v1/episodes/{episode['id']}/panels", headers=other, json={}).status_code
        == 404
    )
    for path in [
        f"/projects/{project['id']}/bible",
        f"/projects/{project['id']}/assets",
        f"/projects/{project['id']}/episodes",
        f"/episodes/{episode['id']}/panels",
    ]:
        assert client.get(f"/api/v1{path}", headers=other).status_code == 404


def test_delete_project_cascades(
    client: TestClient,
    headers: dict[str, str],
    project: dict[str, Any],
    episode: dict[str, Any],
    png: bytes,
) -> None:
    asset = upload_asset(client, headers, project["id"], png)
    panel = client.post(
        f"/api/v1/episodes/{episode['id']}/panels",
        headers=headers,
        json={"image_asset_id": asset["id"]},
    ).json()
    client.patch(
        f"/api/v1/projects/{project['id']}",
        headers=headers,
        json={"thumbnail_asset_id": asset["id"]},
    )
    assert client.delete(f"/api/v1/projects/{project['id']}", headers=headers).status_code == 204
    for path in [f"/episodes/{episode['id']}", f"/panels/{panel['id']}", f"/assets/{asset['id']}"]:
        assert client.get(f"/api/v1{path}", headers=headers).status_code == 404


@pytest.mark.parametrize(
    "data",
    [
        {"title": ""},
        {"title": "  "},
        {"title": "x", "orientation": "diagonal"},
        {"title": "x", "creation_mode": "invalid"},
    ],
)
def test_project_validation(
    client: TestClient, headers: dict[str, str], data: dict[str, str]
) -> None:
    assert client.post("/api/v1/projects", headers=headers, json=data).status_code == 422


def test_health_and_readiness(client: TestClient) -> None:
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/ready").status_code == 200
    config = client.get("/api/v1/config").json()
    assert "local_auth_secret" not in config
    assert "supabase_service_role_key" not in config
    with app.state.session_factory() as db:
        db.execute(text("UPDATE alembic_version SET version_num='outdated'"))
        db.commit()
    assert client.get("/ready").status_code == 503


def test_generation_jobs_use_backend_daily_quotas(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    user_id = UUID(client.get("/api/v1/auth/me", headers=headers).json()["id"])
    project_id = UUID(project["id"])
    settings = Settings(
        _env_file=None,
        local_auth_secret="quota-test-secret-" * 3,
        story_daily_limit=2,
    )
    with app.state.session_factory() as db:
        service = GenerationService(db, user_id, settings)
        service.create_job(project_id, "story", "outline", {"prompt": "first"})
        service.create_job(project_id, "story", "outline", {"prompt": "second"})
        with pytest.raises(ApplicationError, match="Daily story generation limit reached") as error:
            service.create_job(project_id, "story", "outline")
        assert error.value.status == 429
        assert error.value.code == "generation_quota_exceeded"

    quota = client.get("/api/v1/quotas", headers=headers)
    assert quota.status_code == 200
    assert quota.json()["buckets"]["story"] == {"limit": 10, "used": 2, "remaining": 8}
    jobs = client.get("/api/v1/jobs", headers=headers).json()
    assert len(jobs) == 2
    assert jobs[0]["job_type"] == "story:outline"
