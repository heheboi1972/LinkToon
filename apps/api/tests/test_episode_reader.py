from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from conftest import register, upload_asset
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.models import Asset, Scene
from app.storage import storage_for


def test_episode_reader_returns_ordered_story_and_only_media_capabilities(
    client: TestClient,
    headers: dict[str, str],
    project: dict[str, str],
    episode: dict[str, str],
    png: bytes,
) -> None:
    image = upload_asset(client, headers, project["id"], png)
    owner_id = UUID(client.get("/api/v1/auth/me", headers=headers).json()["id"])
    video_bytes = (
        Path(__file__).parents[1] / "app" / "providers" / "fixtures" / "mock-motion.mp4"
    ).read_bytes()
    video_id = uuid4()
    storage_key = f"{owner_id}/{project['id']}/{video_id}"
    settings = get_settings()
    storage_for(settings).put(storage_key, video_bytes, "video/mp4")

    with app.state.session_factory() as db:
        db.add(
            Asset(
                id=video_id,
                owner_id=owner_id,
                project_id=UUID(project["id"]),
                asset_type="video",
                mime_type="video/mp4",
                storage_provider=settings.storage_provider,
                storage_bucket="local",
                storage_key=storage_key,
                source="generated",
                provider="runway",
                provider_task_id="private-provider-task-id",
                prompt="private prompt",
                file_size=len(video_bytes),
                metadata_json={
                    "model": "private-model",
                    "provider_task_id": "private-metadata-task-id",
                    "provider_metadata": {"token": "private-output-token"},
                },
                duration_ms=5000,
                upload_status="ready",
            )
        )
        db.add_all(
            [
                Scene(
                    episode_id=UUID(episode["id"]),
                    position=5,
                    title="Text only",
                    script={"narration": "A quiet ending.", "dialogue": []},
                ),
                Scene(
                    episode_id=UUID(episode["id"]),
                    position=0,
                    title="Opening",
                    image_asset_id=UUID(image["id"]),
                    video_asset_id=video_id,
                    script={
                        "narration": "Mina looks up.",
                        "dialogue": [{"character": "Mina", "text": "There it is."}],
                        "visual_prompt": "must not be returned",
                        "character_ids": ["private-character-id"],
                        "generation_job_id": "private-job-id",
                    },
                ),
                Scene(
                    episode_id=UUID(episode["id"]),
                    position=3,
                    title="Image only",
                    image_asset_id=UUID(image["id"]),
                    script={"narration": "The lights return."},
                ),
            ]
        )
        db.commit()

    response = client.get(f"/api/v1/episodes/{episode['id']}/reader", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["episode_id"] == episode["id"]
    assert body["title"] == episode["title"]
    assert [scene["title"] for scene in body["scenes"]] == [
        "Opening",
        "Image only",
        "Text only",
    ]
    assert [scene["order"] for scene in body["scenes"]] == [1, 2, 3]
    opening = body["scenes"][0]
    assert opening["narration"] == "Mina looks up."
    assert opening["dialogue"] == [{"character": "Mina", "text": "There it is."}]
    assert "/api/v1/assets/" in opening["image_url"]
    assert "/api/v1/assets/" in opening["video_url"]
    assert body["scenes"][1]["video_url"] is None
    assert body["scenes"][2]["image_url"] is None
    assert "private" not in response.text
    assert "visual_prompt" not in response.text
    assert "character_ids" not in response.text

    video_path = urlsplit(opening["video_url"])
    video_response = client.get(
        f"{video_path.path}?{video_path.query}", headers={"Range": "bytes=0-15"}
    )
    assert video_response.status_code == 206
    assert video_response.headers["content-type"].startswith("video/mp4")
    assert video_response.headers["content-range"].startswith("bytes 0-15/")


def test_episode_reader_is_owner_scoped_and_returns_empty_episodes(
    client: TestClient,
    headers: dict[str, str],
    episode: dict[str, str],
) -> None:
    result = client.get(f"/api/v1/episodes/{episode['id']}/reader", headers=headers)
    assert result.status_code == 200
    assert result.json()["scenes"] == []

    other = register(client, "reader-other@example.com")
    assert client.get(f"/api/v1/episodes/{episode['id']}/reader", headers=other).status_code == 404
