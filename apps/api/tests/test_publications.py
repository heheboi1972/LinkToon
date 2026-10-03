from urllib.parse import urlsplit
from uuid import UUID

from conftest import register, upload_asset
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import PublicationScene, Scene


def add_scene(
    episode_id: str, position: int, title: str, narration: str, image_id: str | None = None
) -> UUID:
    with app.state.session_factory() as db:
        scene = Scene(
            episode_id=UUID(episode_id),
            position=position,
            title=title,
            image_asset_id=UUID(image_id) if image_id else None,
            script={
                "narration": narration,
                "dialogue": [{"character": "Mina", "text": "We made it."}],
                "visual_prompt": "never public",
                "character_ids": ["private-character"],
            },
        )
        db.add(scene)
        db.commit()
        return scene.id


def test_publication_is_a_versioned_snapshot_with_scoped_private_media(
    client: TestClient,
    headers: dict[str, str],
    project: dict[str, str],
    episode: dict[str, str],
    png: bytes,
) -> None:
    image = upload_asset(client, headers, project["id"], png)
    scene_id = add_scene(episode["id"], 0, "Rooftop", "The lights return.", image["id"])
    empty_episode = client.post(
        f"/api/v1/projects/{project['id']}/episodes",
        headers=headers,
        json={"title": "Empty"},
    ).json()
    empty_publish = client.post(
        f"/api/v1/episodes/{empty_episode['id']}/publish", headers=headers, json={}
    )
    assert empty_publish.status_code == 422

    response = client.post(
        f"/api/v1/episodes/{episode['id']}/publish",
        headers=headers,
        json={"visibility": "public"},
    )
    assert response.status_code == 201, response.text
    publication = response.json()
    assert publication["current_version"] == 1
    assert publication["scene_count"] == 1
    slug = publication["slug"]

    public = client.get(f"/api/v1/publications/{slug}")
    assert public.status_code == 200, public.text
    body = public.json()
    assert body["title"] == "First light"
    assert body["scenes"][0]["title"] == "Rooftop"
    assert body["scenes"][0]["narration"] == "The lights return."
    assert body["scenes"][0]["dialogue"] == [{"character": "Mina", "text": "We made it."}]
    assert "never public" not in public.text
    assert "private-character" not in public.text
    assert "storage_key" not in public.text
    assert "owner_id" not in public.text
    assert "provider" not in public.text

    media_path = urlsplit(body["scenes"][0]["image_url"])
    image_response = client.get(f"{media_path.path}?{media_path.query}")
    assert image_response.status_code == 200
    assert image_response.content == png

    second_image = upload_asset(client, headers, project["id"], png)
    with app.state.session_factory() as db:
        scene = db.get(Scene, UUID(str(scene_id)))
        assert scene is not None
        scene.title = "Repainted rooftop"
        scene.script = {"narration": "The scene changed in the studio."}
        scene.image_asset_id = UUID(second_image["id"])
        db.commit()
        snapshot_assets = list(db.scalars(select(PublicationScene.image_asset_id)))
        assert UUID(image["id"]) in snapshot_assets

    # Changes to the draft stay private until the explicit republish operation.
    unchanged = client.get(f"/api/v1/publications/{slug}").json()
    assert unchanged["scenes"][0]["title"] == "Rooftop"
    assert unchanged["scenes"][0]["narration"] == "The lights return."
    assert client.delete(f"/api/v1/assets/{image['id']}", headers=headers).status_code == 409

    other = register(client, "publication-other@example.com")
    assert (
        client.patch(
            f"/api/v1/publications/{publication['id']}",
            headers=other,
            json={"title": "Hijack"},
        ).status_code
        == 404
    )

    hidden = client.patch(
        f"/api/v1/publications/{publication['id']}",
        headers=headers,
        json={"visibility": "private"},
    )
    assert hidden.status_code == 200
    assert client.get(f"/api/v1/publications/{slug}").status_code == 404
    # A previously issued URL stops resolving as soon as publication visibility changes.
    assert client.get(f"{media_path.path}?{media_path.query}").status_code == 404

    made_public = client.patch(
        f"/api/v1/publications/{publication['id']}",
        headers=headers,
        json={"visibility": "unlisted"},
    )
    assert made_public.status_code == 200
    assert client.get(f"/api/v1/publications/{slug}").status_code == 200
    republished = client.post(
        f"/api/v1/publications/{publication['id']}/republish", headers=headers
    )
    assert republished.status_code == 200, republished.text
    assert republished.json()["current_version"] == 2
    assert republished.json()["slug"] == slug
    changed = client.get(f"/api/v1/publications/{slug}").json()
    assert changed["scenes"][0]["title"] == "Repainted rooftop"
    assert changed["scenes"][0]["narration"] == "The scene changed in the studio."
    assert changed["scenes"][0]["image_url"] != body["scenes"][0]["image_url"]

    unpublished = client.post(
        f"/api/v1/publications/{publication['id']}/unpublish", headers=headers
    )
    assert unpublished.status_code == 200
    assert unpublished.json()["status"] == "unpublished"
    assert client.get(f"/api/v1/publications/{slug}").status_code == 404
    assert (
        client.get(
            f"{urlsplit(changed['scenes'][0]['image_url']).path}?{urlsplit(changed['scenes'][0]['image_url']).query}"
        ).status_code
        == 404
    )
    restored = client.post(f"/api/v1/publications/{publication['id']}/republish", headers=headers)
    assert restored.status_code == 200
    assert restored.json()["current_version"] == 3
    assert client.get(f"/api/v1/publications/{slug}").status_code == 200


def test_unlisted_publication_and_overview_are_owner_scoped_and_data_backed(
    client: TestClient,
    headers: dict[str, str],
    project: dict[str, str],
    episode: dict[str, str],
) -> None:
    add_scene(episode["id"], 0, "Quiet scene", "A paper lantern moves.")
    created = client.post(
        f"/api/v1/episodes/{episode['id']}/publish",
        headers=headers,
        json={"visibility": "unlisted"},
    )
    assert created.status_code == 201
    publication = created.json()
    assert client.get(f"/api/v1/publications/{publication['slug']}").status_code == 200
    assert (
        client.get(f"/api/v1/episodes/{episode['id']}/publication", headers=headers).json()["slug"]
        == publication["slug"]
    )

    overview = client.get(f"/api/v1/projects/{project['id']}/overview", headers=headers)
    assert overview.status_code == 200
    assert overview.json()["episode_count"] == 1
    assert overview.json()["scene_count"] == 1
    assert overview.json()["image_count"] == 0
    assert overview.json()["motion_count"] == 0
    assert overview.json()["published_count"] == 1

    other = register(client, "overview-other@example.com")
    assert (
        client.get(f"/api/v1/projects/{project['id']}/overview", headers=other).status_code == 404
    )
