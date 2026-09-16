import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from alembic.script import ScriptDirectory
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.db import session_factory
from app.errors import ApplicationError
from app.logging import SensitiveDataFilter
from app.routes import router

logger = logging.getLogger(__name__)
settings = get_settings()
log_filter = SensitiveDataFilter(
    [
        settings.local_auth_secret,
        settings.supabase_service_role_key,
        settings.openai_api_key,
        settings.fal_key,
        settings.runwayml_api_secret,
    ]
)
for logger_name in ("uvicorn.access", "uvicorn.error", "app"):
    logging.getLogger(logger_name).addFilter(log_filter)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    application.state.session_factory = session_factory()
    application.state.schema_heads = set(
        ScriptDirectory(str(Path(__file__).resolve().parents[1] / "alembic")).get_heads()
    )
    yield
    application.state.session_factory.kw["bind"].dispose()


app = FastAPI(title="LinkToon API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(router)


@app.exception_handler(ApplicationError)
async def application_error(request: Request, exc: ApplicationError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}}
    )


@app.exception_handler(IntegrityError)
async def integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
    logger.warning("Database constraint conflict: %s", type(exc.orig).__name__)
    return JSONResponse(
        status_code=409,
        content={
            "error": {
                "code": "conflict",
                "message": "This change conflicts with existing data. Refresh and retry.",
            }
        },
    )


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "linktoon-api", "phase": "1"}


@app.get("/ready", tags=["system"])
def ready() -> dict[str, str]:
    try:
        with app.state.session_factory() as db:
            versions = set(db.scalars(text("SELECT version_num FROM alembic_version")))
            if versions != app.state.schema_heads:
                raise ValueError("Database revision does not match the application")
    except Exception as exc:
        raise ApplicationError(
            "Database migration is required or DB unavailable", "not_ready", 503
        ) from exc
    return {"status": "ready"}
