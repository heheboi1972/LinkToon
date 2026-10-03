import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.main import app


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="RLS requires PostgreSQL")
def test_supabase_rls_owner_and_password_isolation(
    client: TestClient, headers: dict[str, str], project: dict[str, Any]
) -> None:
    owner = client.get("/api/v1/auth/me", headers=headers).json()["id"]
    engine = app.state.session_factory.kw["bind"]
    # Reproduce Supabase's platform roles and auth.uid in this disposable database only.
    with engine.begin() as connection:
        connection.exec_driver_sql("""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon') THEN
                    CREATE ROLE anon NOLOGIN;
                    CREATE ROLE authenticated NOLOGIN;
                    CREATE ROLE service_role NOLOGIN BYPASSRLS;
                END IF;
            END $$;
            CREATE SCHEMA auth;
            CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$
                SELECT nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
            $$;
            GRANT USAGE ON SCHEMA auth, public TO authenticated, anon;
            CREATE SCHEMA storage;
            CREATE TABLE storage.buckets (
                id text PRIMARY KEY, name text, public boolean,
                file_size_limit bigint, allowed_mime_types text[]
            );
        """)
        sql = (Path(__file__).resolve().parents[3] / "scripts" / "supabase-rls.sql").read_text()
        sql = sql.replace("BEGIN;", "", 1).rsplit("COMMIT;", 1)[0]
        connection.exec_driver_sql(sql)
    with engine.begin() as connection:
        assert connection.scalar(text("SELECT public FROM storage.buckets")) is False
        assert (
            connection.scalar(
                text("SELECT count(*) FROM pg_tables WHERE schemaname='public' AND rowsecurity")
            )
            == 17
        )
        connection.execute(text("SET LOCAL ROLE authenticated"))
        connection.execute(
            text("SELECT set_config('request.jwt.claim.sub', :owner, true)"), {"owner": owner}
        )
        assert connection.scalar(text("SELECT count(*) FROM public.projects")) == 1
        assert connection.scalar(text("SELECT count(*) FROM public.project_bibles")) == 1
        connection.execute(
            text("SELECT set_config('request.jwt.claim.sub', :other, true)"),
            {"other": str(uuid4())},
        )
        assert connection.scalar(text("SELECT count(*) FROM public.projects")) == 0
    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(text("SET LOCAL ROLE authenticated"))
        connection.execute(text("SELECT password_hash FROM public.profiles"))
    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(text("SET LOCAL ROLE authenticated"))
        connection.execute(text("DELETE FROM public.projects"))
    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(text("SET LOCAL ROLE anon"))
        connection.execute(text("SELECT * FROM public.projects"))
    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(text("SET LOCAL ROLE anon"))
        connection.execute(text("SELECT * FROM public.publication_scenes"))
