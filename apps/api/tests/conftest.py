import os
from collections.abc import Generator
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from alembic import command

os.environ["APP_ENV"] = "test"
os.environ["AUTH_MODE"] = "local"
os.environ["STORAGE_PROVIDER"] = "local"
os.environ["LOCAL_AUTH_SECRET"] = "test-secret-" * 8

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    postgres_url = os.getenv("TEST_POSTGRES_URL")
    admin = None
    database = "linktoon_test_" + uuid4().hex
    if postgres_url:
        admin = create_engine(postgres_url, isolation_level="AUTOCOMMIT")
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{database}"'))
        url = make_url(postgres_url).set(database=database).render_as_string(hide_password=False)
    else:
        url = f"sqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path / "assets"))
    get_settings.cache_clear()
    try:
        command.upgrade(Config("alembic.ini"), "head")
        with TestClient(app) as test_client:
            yield test_client
    finally:
        get_settings.cache_clear()
        if admin:
            with admin.connect() as connection:
                connection.execute(text(f'DROP DATABASE "{database}"'))
            admin.dispose()


def register(client: TestClient, email: str = "artist@example.com") -> dict[str, str]:
    result = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "long-password-123", "display_name": "Artist"},
    )
    assert result.status_code == 201, result.text
    return {"Authorization": f"Bearer {result.json()['access_token']}"}


@pytest.fixture
def headers(client: TestClient) -> dict[str, str]:
    return register(client)


@pytest.fixture
def project(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = client.post(
        "/api/v1/projects", headers=headers, json={"title": "Moonlight", "visual_style": "ink"}
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def episode(client: TestClient, headers: dict[str, str], project: dict[str, Any]) -> dict[str, Any]:
    return client.post(
        f"/api/v1/projects/{project['id']}/episodes", headers=headers, json={"title": "First light"}
    ).json()


@pytest.fixture
def png() -> bytes:
    content = BytesIO()
    Image.new("RGB", (48, 64), "#6d28d9").save(content, "PNG")
    return content.getvalue()


def upload_asset(
    client: TestClient, headers: dict[str, str], project_id: str, content: bytes
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/assets/upload-url",
        headers=headers,
        json={
            "project_id": project_id,
            "filename": "panel.png",
            "mime_type": "image/png",
            "file_size": len(content),
        },
    )
    assert response.status_code == 201, response.text
    ticket = response.json()
    uploaded = client.put(
        ticket["upload_url"], content=content, headers={"Content-Type": "image/png"}
    )
    assert uploaded.status_code == 204, uploaded.text
    completed = client.post(
        "/api/v1/assets/complete", headers=headers, json={"asset_id": ticket["asset_id"]}
    )
    assert completed.status_code == 200, completed.text
    return completed.json()
