import logging
from datetime import UTC, datetime
from io import StringIO
from typing import Any
from uuid import uuid4

import httpx
import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import MetaData, Table, inspect, select
from uvicorn.logging import AccessFormatter

from alembic import command
from app.auth import sign_token, supabase_identity, verify_token
from app.config import Settings, get_settings
from app.errors import ApplicationError, StorageError
from app.logging import RedactCapabilityQuery, SensitiveDataFilter
from app.main import app
from app.storage import SupabaseStorage


def test_migration_roundtrip_and_drift(client: TestClient) -> None:
    config = Config("alembic.ini")
    command.check(config)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    with app.state.session_factory() as db:
        assert set(inspect(db.bind).get_table_names()) == {
            "alembic_version",
            "profiles",
            "projects",
            "project_bibles",
            "characters",
            "character_references",
            "episodes",
            "scenes",
            "panels",
            "assets",
            "motion_plans",
            "motion_layers",
            "animations",
            "generation_jobs",
            "publish_versions",
            "publications",
            "publication_snapshots",
            "publication_scenes",
        }


def test_postgresql_migration_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://test:test@localhost/test")
    get_settings.cache_clear()
    output = StringIO()
    config = Config("alembic.ini", output_buffer=output)
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    assert "JSONB" in sql
    assert "ALTER TABLE projects ADD CONSTRAINT fk_projects_thumbnail" in sql
    assert sql.count("CREATE TABLE ") == 18
    assert "CREATE TABLE publications" in sql
    assert "ON DELETE RESTRICT" in sql
    get_settings.cache_clear()


def test_generation_migration_preserves_existing_rows(client: TestClient) -> None:
    config = Config("alembic.ini")
    command.downgrade(config, "0001")
    owner_id = uuid4()
    project_id = uuid4()
    job_id = uuid4()
    asset_id = uuid4()
    now = datetime.now(UTC)

    with app.state.session_factory() as db:
        sqlite = db.bind is not None and db.bind.dialect.name == "sqlite"
        db_owner_id = owner_id.hex if sqlite else owner_id
        db_project_id = project_id.hex if sqlite else project_id
        db_job_id = job_id.hex if sqlite else job_id
        db_asset_id = asset_id.hex if sqlite else asset_id
        metadata = MetaData()
        profiles = Table("profiles", metadata, autoload_with=db.bind)
        projects = Table("projects", metadata, autoload_with=db.bind)
        jobs = Table("generation_jobs", metadata, autoload_with=db.bind)
        assets = Table("assets", metadata, autoload_with=db.bind)
        db.execute(
            profiles.insert().values(
                id=db_owner_id,
                email="migration@example.com",
                display_name="Migration",
                password_hash=None,
                created_at=now,
                updated_at=now,
            )
        )
        db.execute(
            projects.insert().values(
                id=db_project_id,
                owner_id=db_owner_id,
                title="Preserved",
                description="",
                genre="fantasy",
                orientation="vertical",
                creation_mode="manual",
                status="draft",
                thumbnail_asset_id=None,
                created_at=now,
                updated_at=now,
            )
        )
        db.execute(
            jobs.insert().values(
                id=db_job_id,
                user_id=db_owner_id,
                project_id=db_project_id,
                job_type="motion:panel",
                status="postprocessing",
                input={"panel": 1},
                output={},
                progress=75,
                created_at=now,
            )
        )
        db.execute(
            assets.insert().values(
                id=db_asset_id,
                owner_id=db_owner_id,
                project_id=db_project_id,
                asset_type="image",
                mime_type="image/png",
                storage_provider="local",
                storage_key=f"{owner_id}/{project_id}/{asset_id}",
                file_size=64,
                metadata={"filename": "preserved.png"},
                upload_status="ready",
                created_at=now,
            )
        )
        db.commit()

    command.upgrade(config, "head")

    with app.state.session_factory() as db:
        metadata = MetaData()
        jobs = Table("generation_jobs", metadata, autoload_with=db.bind)
        assets = Table("assets", metadata, autoload_with=db.bind)
        job = db.execute(select(jobs).where(jobs.c.id == db_job_id)).mappings().one()
        asset = db.execute(select(assets).where(assets.c.id == db_asset_id)).mappings().one()
        assert job["status"] == "saving"
        assert job["retry_count"] == 0
        assert job["provider_output"] == {}
        assert job["updated_at"] is not None
        assert asset["source"] == "upload"
        assert asset["storage_bucket"] is None


def test_production_disallows_local_auth() -> None:
    with pytest.raises(ValidationError, match="Production requires Supabase"):
        Settings(_env_file=None, app_env="production")


def test_capability_purpose_and_expiry() -> None:
    settings = Settings(_env_file=None)
    subject = uuid4()
    token = sign_token(settings, subject, "upload", minutes=1)
    assert verify_token(settings, token, "upload") == subject
    with pytest.raises(ApplicationError):
        verify_token(settings, token, "session")
    with pytest.raises(ApplicationError):
        verify_token(settings, sign_token(settings, subject, "session", minutes=-1), "session")


def test_access_log_redacts_capability_tokens() -> None:
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "test",
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("localhost", "GET", "/api/v1/assets/id/content?token=private", "1.1", 200),
        None,
    )
    assert RedactCapabilityQuery().filter(record)
    assert "private" not in record.getMessage()
    assert "/api/v1/assets/id/content" in record.getMessage()


def test_access_log_formatter_keeps_uvicorn_arguments_and_redacts_secrets() -> None:
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "test",
        1,
        '%s - "%s %s HTTP/%s" %d',
        (
            "localhost",
            "GET",
            "/api/v1/assets/id/content?token=private-token&key=another-secret",
            "1.1",
            200,
        ),
        None,
    )
    assert SensitiveDataFilter(["another-secret"]).filter(record)
    assert len(record.args) == 5
    formatted = AccessFormatter(
        fmt='%(client_addr)s - "%(request_line)s" %(status_code)s', use_colors=False
    ).format(record)
    assert "GET /api/v1/assets/id/content HTTP/1.1" in formatted
    assert "200 OK" in formatted
    assert "private-token" not in formatted
    assert "another-secret" not in formatted
    assert "?" not in formatted


def test_application_log_redacts_credentials() -> None:
    log_filter = SensitiveDataFilter(["configured-provider-secret"])
    record = logging.LogRecord(
        "app.provider",
        logging.ERROR,
        "test",
        1,
        "provider failed: Authorization=Bearer abc.def password=hunter2 key=%s raw=%s",
        ("api-value", "configured-provider-secret"),
        None,
    )
    assert log_filter.filter(record)
    message = record.getMessage()
    for value in ("abc.def", "hunter2", "api-value", "configured-provider-secret"):
        assert value not in message


def test_supabase_auth_remote_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        _env_file=None, supabase_url="https://project.supabase.co", supabase_anon_key="public-anon"
    )
    subject = str(uuid4())

    def get(url: str, **kwargs: Any) -> httpx.Response:
        assert url.endswith("/auth/v1/user")
        assert kwargs["headers"]["Authorization"] == "Bearer remote-token"
        return httpx.Response(
            200,
            json={"id": subject, "email": "artist@example.com"},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", get)
    assert supabase_identity("remote-token", settings)["id"] == subject


def test_supabase_storage_never_upserts_and_handles_outage(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        _env_file=None,
        supabase_url="https://project.supabase.co",
        supabase_service_role_key="service-secret",
    )
    storage = SupabaseStorage(settings)

    def post(url: str, **kwargs: Any) -> httpx.Response:
        assert kwargs["headers"]["x-upsert"] == "false"
        assert kwargs["headers"]["Authorization"] == "Bearer service-secret"
        return httpx.Response(201, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)
    storage.put("owner/project/asset", b"image", "image/png")

    def fail(url: str, **kwargs: Any) -> httpx.Response:
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "get", fail)
    with pytest.raises(StorageError):
        storage.read("owner/project/asset")
