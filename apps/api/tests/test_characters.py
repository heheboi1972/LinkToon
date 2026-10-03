from typing import Any
from uuid import UUID

from conftest import register
from fastapi.testclient import TestClient

from app.main import app
from app.models import Character


def test_project_characters_are_scoped_to_owner_and_project(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    path = f"/api/v1/projects/{project['id']}/characters"
    assert client.get(path, headers=headers).json() == []

    other_headers = register(client, "second-artist@example.com")
    other_project_response = client.post(
        "/api/v1/projects", headers=other_headers, json={"title": "Other world"}
    )
    assert other_project_response.status_code == 201
    other_project_id = UUID(other_project_response.json()["id"])
    with app.state.session_factory() as db:
        alice = Character(project_id=UUID(project["id"]), name="Alice", description="Detective")
        bob = Character(project_id=UUID(project["id"]), name="Bob", description="Pilot")
        outsider = Character(project_id=other_project_id, name="Outsider", description="Private")
        db.add_all([bob, outsider, alice])
        db.commit()

    response = client.get(path, headers=headers)
    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(alice.id),
            "project_id": project["id"],
            "name": "Alice",
            "description": "Detective",
        },
        {
            "id": str(bob.id),
            "project_id": project["id"],
            "name": "Bob",
            "description": "Pilot",
        },
    ]
    page = client.get(path, headers=headers, params={"limit": 1, "offset": 1})
    assert [item["name"] for item in page.json()] == ["Bob"]
    assert client.get(path).status_code == 401
    assert client.get(path, headers=other_headers).status_code == 404
    other_path = f"/api/v1/projects/{other_project_id}/characters"
    assert client.get(other_path, headers=headers).status_code == 404
