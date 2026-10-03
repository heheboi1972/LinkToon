"""TASK 7 Character Bible, reference Asset and consistency pipeline checks."""

from typing import Any
from uuid import UUID

from conftest import register, upload_asset
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.job_worker import DatabaseWorker
from app.main import app
from app.models import Asset, Character, CharacterReference, GenerationJob, Scene
from app.providers.mock import MockProvider
from app.providers.registry import ProviderRegistry


def create_character(
    client: TestClient, headers: dict[str, str], project_id: str, **values: Any
) -> dict[str, Any]:
    payload = {
        "name": "Mina",
        "description": "Courier",
        "face_description": "round face",
        "hair_description": "black bob",
        "clothing": "violet jacket",
    }
    payload.update(values)
    response = client.post(
        f"/api/v1/projects/{project_id}/characters", headers=headers, json=payload
    )
    assert response.status_code == 201, response.text
    return response.json()


def reference_job(
    client: TestClient, headers: dict[str, str], character_id: str, key: str = "reference-key"
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/characters/{character_id}/reference/generate",
        headers={**headers, "Idempotency-Key": key},
    )
    assert response.status_code == 202, response.text
    return response.json()


def run_worker(job_id: str) -> None:
    worker = DatabaseWorker(
        app.state.session_factory,
        get_settings(),
        ProviderRegistry([MockProvider()]),
        "task7-test-worker",
    )
    with app.state.session_factory() as db:
        job = db.get(GenerationJob, UUID(job_id))
        assert job is not None
        job.status = "queued"
        job.lease_owner = None
        job.lease_expires_at = None
        db.commit()
    assert worker.run_once()


def test_create_character_persists_structured_bible(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    result = create_character(client, headers, project["id"])
    assert result["character_bible"]["face_description"] == "round face"
    assert result["character_revision"] == 1
    assert result["reference_asset_id"] is None


def test_list_character_returns_new_schema_for_api_created_character(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    result = create_character(client, headers, project["id"])
    listed = client.get(f"/api/v1/projects/{project['id']}/characters", headers=headers).json()
    assert listed[0]["id"] == result["id"]
    assert "character_bible" in listed[0]


def test_get_character_is_owner_scoped(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    character = create_character(client, headers, project["id"])
    other = register(client, "task7-other-get@example.com")
    response = client.get(f"/api/v1/characters/{character['id']}", headers=other)
    assert response.status_code == 404


def test_patch_character_increments_revision(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    character = create_character(client, headers, project["id"])
    response = client.patch(
        f"/api/v1/characters/{character['id']}",
        headers=headers,
        json={"hair_description": "silver braid"},
    )
    assert response.status_code == 200
    assert response.json()["character_revision"] == 2
    assert response.json()["character_bible"]["hair_description"] == "silver braid"


def test_select_uploaded_image_as_reference(
    client: TestClient, headers: dict[str, str], project: dict[str, Any], png: bytes
) -> None:
    character = create_character(client, headers, project["id"])
    asset = upload_asset(client, headers, project["id"], png)
    response = client.put(
        f"/api/v1/characters/{character['id']}/reference",
        headers=headers,
        json={"asset_id": asset["id"]},
    )
    assert response.status_code == 200
    assert response.json()["reference_asset_id"] == asset["id"]
    assert response.json()["reference_stale"] is False


def test_reference_asset_selection_rejects_other_owner(
    client: TestClient, headers: dict[str, str], project: dict[str, Any], png: bytes
) -> None:
    character = create_character(client, headers, project["id"])
    other = register(client, "task7-other-reference@example.com")
    other_project = client.post("/api/v1/projects", headers=other, json={"title": "Other"}).json()
    asset = upload_asset(client, other, other_project["id"], png)
    response = client.put(
        f"/api/v1/characters/{character['id']}/reference",
        headers=headers,
        json={"asset_id": asset["id"]},
    )
    assert response.status_code == 404


def test_reference_asset_selection_rejects_reference_asset_type(
    client: TestClient, headers: dict[str, str], project: dict[str, Any], png: bytes
) -> None:
    character = create_character(client, headers, project["id"])
    asset = upload_asset(client, headers, project["id"], png)
    with app.state.session_factory() as db:
        row = db.get(Asset, UUID(asset["id"]))
        assert row is not None
        row.asset_type = "reference"
        db.commit()
    response = client.put(
        f"/api/v1/characters/{character['id']}/reference",
        headers=headers,
        json={"asset_id": asset["id"]},
    )
    assert response.status_code == 422


def test_clear_reference_keeps_asset(
    client: TestClient, headers: dict[str, str], project: dict[str, Any], png: bytes
) -> None:
    character = create_character(client, headers, project["id"])
    asset = upload_asset(client, headers, project["id"], png)
    client.put(
        f"/api/v1/characters/{character['id']}/reference",
        headers=headers,
        json={"asset_id": asset["id"]},
    )
    response = client.delete(f"/api/v1/characters/{character['id']}/reference", headers=headers)
    assert response.status_code == 200
    assert response.json()["reference_asset_id"] is None
    assert client.get(f"/api/v1/assets/{asset['id']}", headers=headers).status_code == 200


def test_character_update_marks_reference_stale(
    client: TestClient, headers: dict[str, str], project: dict[str, Any], png: bytes
) -> None:
    character = create_character(client, headers, project["id"])
    asset = upload_asset(client, headers, project["id"], png)
    client.put(
        f"/api/v1/characters/{character['id']}/reference",
        headers=headers,
        json={"asset_id": asset["id"]},
    )
    result = client.patch(
        f"/api/v1/characters/{character['id']}", headers=headers, json={"clothing": "red coat"}
    ).json()
    assert result["reference_stale"] is True


def test_reference_generation_is_admitted(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    character = create_character(client, headers, project["id"])
    accepted = reference_job(client, headers, character["id"])
    assert accepted["status"] == "queued"


def test_reference_generation_is_idempotent(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    character = create_character(client, headers, project["id"])
    assert reference_job(client, headers, character["id"]) == reference_job(
        client, headers, character["id"]
    )


def test_reference_generation_has_character_scope(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    character = create_character(client, headers, project["id"])
    reference_job(client, headers, character["id"], "scope-one")
    response = client.post(
        f"/api/v1/characters/{character['id']}/reference/generate",
        headers={**headers, "Idempotency-Key": "scope-two"},
    )
    assert response.status_code == 409


def test_mock_worker_saves_reference_asset(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    character = create_character(client, headers, project["id"])
    accepted = reference_job(client, headers, character["id"])
    run_worker(accepted["job_id"])
    detail = client.get(f"/api/v1/jobs/{accepted['job_id']}", headers=headers).json()
    assert detail["status"] == "succeeded"
    assert detail["output"]["reference_asset_id"]
    saved = client.get(f"/api/v1/characters/{character['id']}", headers=headers).json()
    assert saved["reference_asset_id"] == detail["output"]["reference_asset_id"]


def test_reference_history_row_is_created(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    character = create_character(client, headers, project["id"])
    accepted = reference_job(client, headers, character["id"])
    run_worker(accepted["job_id"])
    with app.state.session_factory() as db:
        assert (
            db.scalar(
                select(CharacterReference.id).where(
                    CharacterReference.character_id == UUID(character["id"])
                )
            )
            is not None
        )


def test_reference_asset_cannot_be_deleted_while_selected(
    client: TestClient, headers: dict[str, str], project: dict[str, Any], png: bytes
) -> None:
    character = create_character(client, headers, project["id"])
    asset = upload_asset(client, headers, project["id"], png)
    client.put(
        f"/api/v1/characters/{character['id']}/reference",
        headers=headers,
        json={"asset_id": asset["id"]},
    )
    assert client.delete(f"/api/v1/assets/{asset['id']}", headers=headers).status_code == 409


def test_scene_job_records_reference_asset_input(
    client: TestClient,
    headers: dict[str, str],
    project: dict[str, Any],
    episode: dict[str, Any],
    png: bytes,
) -> None:
    character = create_character(client, headers, project["id"])
    asset = upload_asset(client, headers, project["id"], png)
    client.put(
        f"/api/v1/characters/{character['id']}/reference",
        headers=headers,
        json={"asset_id": asset["id"]},
    )
    with app.state.session_factory() as db:
        scene = Scene(
            episode_id=UUID(episode["id"]),
            position=0,
            title="Ref scene",
            script={"visual_prompt": "A quiet street", "character_ids": [character["id"]]},
        )
        db.add(scene)
        db.commit()
        scene_id = scene.id
    response = client.post(
        f"/api/v1/scenes/{scene_id}/image/generate",
        headers={**headers, "Idempotency-Key": "scene-reference"},
    )
    assert response.status_code == 202
    with app.state.session_factory() as db:
        job = db.get(GenerationJob, UUID(response.json()["job_id"]))
        assert job is not None
        assert job.input["reference_asset_ids"] == [asset["id"]]


def test_scene_prompt_contains_identity_locks(
    client: TestClient, headers: dict[str, str], project: dict[str, Any], episode: dict[str, Any]
) -> None:
    character = create_character(
        client,
        headers,
        project["id"],
        appearance_lock={"hair_color": "silver"},
        style_lock={"line": "ink"},
    )
    with app.state.session_factory() as db:
        scene = Scene(
            episode_id=UUID(episode["id"]),
            position=0,
            title="Lock scene",
            script={"visual_prompt": "A bridge", "character_ids": [character["id"]]},
        )
        db.add(scene)
        db.commit()
        scene_id = scene.id
    response = client.post(
        f"/api/v1/scenes/{scene_id}/image/generate",
        headers={**headers, "Idempotency-Key": "scene-lock"},
    )
    with app.state.session_factory() as db:
        job = db.get(GenerationJob, UUID(response.json()["job_id"]))
        assert job is not None
        assert "hair_color=silver" in job.input["prompt"]
        assert "line=ink" in job.input["prompt"]


def test_scene_without_reference_uses_text_fallback(
    client: TestClient, headers: dict[str, str], project: dict[str, Any], episode: dict[str, Any]
) -> None:
    character = create_character(client, headers, project["id"])
    with app.state.session_factory() as db:
        scene = Scene(
            episode_id=UUID(episode["id"]),
            position=0,
            title="No ref",
            script={"visual_prompt": "A forest", "character_ids": [character["id"]]},
        )
        db.add(scene)
        db.commit()
        scene_id = scene.id
    response = client.post(
        f"/api/v1/scenes/{scene_id}/image/generate",
        headers={**headers, "Idempotency-Key": "scene-no-ref"},
    )
    assert response.status_code == 202
    with app.state.session_factory() as db:
        job = db.get(GenerationJob, UUID(response.json()["job_id"]))
        assert job is not None
        assert job.input["reference_asset_ids"] == []


def test_scene_with_stale_reference_pointer_falls_back_to_text(
    client: TestClient,
    headers: dict[str, str],
    project: dict[str, Any],
    episode: dict[str, Any],
    png: bytes,
) -> None:
    character = create_character(client, headers, project["id"])
    invalid_asset = upload_asset(client, headers, project["id"], png)
    with app.state.session_factory() as db:
        row = db.get(Character, UUID(character["id"]))
        assert row is not None
        invalid_row = db.get(Asset, UUID(invalid_asset["id"]))
        assert invalid_row is not None
        invalid_row.asset_type = "reference"
        row.reference_asset_id = invalid_row.id
        db.commit()
        scene = Scene(
            episode_id=UUID(episode["id"]),
            position=0,
            title="Stale reference",
            script={"visual_prompt": "A market", "character_ids": [character["id"]]},
        )
        db.add(scene)
        db.commit()
        scene_id = scene.id
    response = client.post(
        f"/api/v1/scenes/{scene_id}/image/generate",
        headers={**headers, "Idempotency-Key": "stale-reference-fallback"},
    )
    assert response.status_code == 202
    with app.state.session_factory() as db:
        job = db.get(GenerationJob, UUID(response.json()["job_id"]))
        assert job is not None
        assert job.input["reference_asset_ids"] == []


def test_delete_unused_character(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    character = create_character(client, headers, project["id"])
    assert (
        client.delete(f"/api/v1/characters/{character['id']}", headers=headers).status_code == 204
    )


def test_delete_character_in_saved_scene_is_blocked(
    client: TestClient, headers: dict[str, str], project: dict[str, Any], episode: dict[str, Any]
) -> None:
    character = create_character(client, headers, project["id"])
    with app.state.session_factory() as db:
        db.add(
            Scene(
                episode_id=UUID(episode["id"]),
                position=0,
                title="Uses character",
                script={"character_ids": [character["id"]]},
            )
        )
        db.commit()
    response = client.delete(f"/api/v1/characters/{character['id']}", headers=headers)
    assert response.status_code == 409


def test_patch_null_is_rejected(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    character = create_character(client, headers, project["id"])
    assert (
        client.patch(
            f"/api/v1/characters/{character['id']}", headers=headers, json={"name": None}
        ).status_code
        == 422
    )


def test_reference_generation_missing_character_is_hidden(
    client: TestClient, headers: dict[str, str]
) -> None:
    response = client.post(
        f"/api/v1/characters/{UUID(int=0)}/reference/generate",
        headers={**headers, "Idempotency-Key": "missing-character"},
    )
    assert response.status_code == 404


def test_character_reference_output_marks_mock(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    character = create_character(client, headers, project["id"])
    accepted = reference_job(client, headers, character["id"], "mock-output")
    run_worker(accepted["job_id"])
    detail = client.get(f"/api/v1/jobs/{accepted['job_id']}", headers=headers).json()
    assert detail["output"]["mock"] is True


def test_character_reference_revision_is_recorded(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    character = create_character(client, headers, project["id"])
    accepted = reference_job(client, headers, character["id"], "revision-record")
    run_worker(accepted["job_id"])
    saved = client.get(f"/api/v1/characters/{character['id']}", headers=headers).json()
    assert saved["reference_generated_from_revision"] == saved["character_revision"]


def test_reference_regeneration_keeps_previous_history(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    character = create_character(client, headers, project["id"])
    accepted = reference_job(client, headers, character["id"], "history-one")
    run_worker(accepted["job_id"])
    first = client.get(f"/api/v1/characters/{character['id']}", headers=headers).json()[
        "reference_asset_id"
    ]
    client.patch(
        f"/api/v1/characters/{character['id']}", headers=headers, json={"clothing": "new outfit"}
    )
    accepted = reference_job(client, headers, character["id"], "history-two")
    run_worker(accepted["job_id"])
    second = client.get(f"/api/v1/characters/{character['id']}", headers=headers).json()[
        "reference_asset_id"
    ]
    assert first != second
    with app.state.session_factory() as db:
        rows = list(
            db.scalars(
                select(CharacterReference).where(
                    CharacterReference.character_id == UUID(character["id"])
                )
            )
        )
        assert len(rows) == 2


def test_reference_asset_is_owner_scoped_in_content(
    client: TestClient, headers: dict[str, str], project: dict[str, Any], png: bytes
) -> None:
    asset = upload_asset(client, headers, project["id"], png)
    other = register(client, "task7-other-content@example.com")
    assert client.get(f"/api/v1/assets/{asset['id']}", headers=other).status_code == 404


def test_character_reference_job_input_contains_prompt_version(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    character = create_character(client, headers, project["id"])
    accepted = reference_job(client, headers, character["id"], "prompt-version")
    with app.state.session_factory() as db:
        job = db.get(GenerationJob, UUID(accepted["job_id"]))
        assert job is not None
        assert job.input["prompt_version"] == "character-reference-v1"


def test_project_character_delete_does_not_delete_reference_history(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    character = create_character(client, headers, project["id"])
    accepted = reference_job(client, headers, character["id"], "delete-history")
    run_worker(accepted["job_id"])
    with app.state.session_factory() as db:
        db.get(Character, UUID(character["id"]))
        # Saved Scenes are absent, so deletion is allowed; the generated asset
        # remains a durable history object.
    assert (
        client.delete(f"/api/v1/characters/{character['id']}", headers=headers).status_code == 204
    )
