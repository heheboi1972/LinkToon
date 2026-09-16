from typing import Any
from uuid import uuid4

from conftest import register, upload_asset
from fastapi.testclient import TestClient


def ticket(
    client: TestClient, headers: dict[str, str], project_id: str, size: int
) -> dict[str, Any]:
    return client.post(
        "/api/v1/assets/upload-url",
        headers=headers,
        json={
            "project_id": project_id,
            "filename": "test.png",
            "mime_type": "image/png",
            "file_size": size,
        },
    ).json()


def test_upload_content_permission_and_immutability(
    client: TestClient, headers: dict[str, str], project: dict[str, Any], png: bytes
) -> None:
    t = ticket(client, headers, project["id"], len(png))
    path = f"/api/v1/assets/{t['asset_id']}"
    assert (
        client.post(
            "/api/v1/assets/complete", headers=headers, json={"asset_id": t["asset_id"]}
        ).status_code
        == 409
    )
    assert (
        client.put(t["upload_url"], content=png, headers={"Content-Type": "image/png"}).status_code
        == 204
    )
    assert (
        client.put(t["upload_url"], content=png, headers={"Content-Type": "image/png"}).status_code
        == 409
    )
    result = client.post(
        "/api/v1/assets/complete", headers=headers, json={"asset_id": t["asset_id"]}
    )
    assert result.status_code == 200, result.text
    asset = result.json()
    assert asset["width"] == 48 and asset["height"] == 64
    assert asset["metadata"]["filename"] == "test.png"
    assert client.get(asset["public_url"]).content == png
    assert client.get(path).status_code == 401
    assert client.get(f"{path}/content?token=invalid").status_code == 401
    other = register(client, "other@example.com")
    assert client.get(path, headers=other).status_code == 404
    assert client.delete(path, headers=other).status_code == 404
    assert (
        client.post(
            "/api/v1/assets/complete", headers=other, json={"asset_id": t["asset_id"]}
        ).status_code
        == 404
    )
    assert client.delete(path, headers=headers).status_code == 204
    assert client.get(asset["public_url"]).status_code == 404


def test_upload_rejects_false_mime_and_oversize(
    client: TestClient, headers: dict[str, str], project: dict[str, Any], png: bytes
) -> None:
    t = ticket(client, headers, project["id"], len(png))
    assert (
        client.put(t["upload_url"], content=png, headers={"Content-Type": "image/jpeg"}).status_code
        == 415
    )
    assert (
        client.put(
            t["upload_url"], content=b"x" * len(png), headers={"Content-Type": "image/png"}
        ).status_code
        == 415
    )
    assert (
        client.put(t["upload_url"], content=b"x", headers={"Content-Type": "image/png"}).status_code
        == 413
    )
    result = client.post(
        "/api/v1/assets/upload-url",
        headers=headers,
        json={
            "project_id": project["id"],
            "filename": "huge.png",
            "mime_type": "image/png",
            "file_size": 10 * 1024 * 1024 + 1,
        },
    )
    assert result.status_code == 413
    assert (
        client.post(
            "/api/v1/assets/upload-url",
            headers=headers,
            json={
                "project_id": project["id"],
                "filename": "bad.svg",
                "mime_type": "image/svg+xml",
                "file_size": 5,
            },
        ).status_code
        == 422
    )
    assert (
        client.put(
            t["upload_url"].replace(t["asset_id"], str(uuid4()), 1),
            content=png,
            headers={"Content-Type": "image/png"},
        ).status_code
        == 401
    )


def test_assets_cannot_cross_projects(
    client: TestClient,
    headers: dict[str, str],
    project: dict[str, Any],
    episode: dict[str, Any],
    png: bytes,
) -> None:
    other_project = client.post(
        "/api/v1/projects", headers=headers, json={"title": "Second"}
    ).json()
    asset = upload_asset(client, headers, other_project["id"], png)
    assert (
        client.post(
            f"/api/v1/episodes/{episode['id']}/panels",
            headers=headers,
            json={"image_asset_id": asset["id"]},
        ).status_code
        == 400
    )
    assert (
        client.patch(
            f"/api/v1/projects/{project['id']}",
            headers=headers,
            json={"thumbnail_asset_id": asset["id"]},
        ).status_code
        == 400
    )
    pending = ticket(client, headers, project["id"], len(png))
    assert (
        client.post(
            f"/api/v1/episodes/{episode['id']}/panels",
            headers=headers,
            json={"image_asset_id": pending["asset_id"]},
        ).status_code
        == 400
    )
