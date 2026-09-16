from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app import auth
from app.assets import AssetService
from app.auth import DB, Config, User
from app.errors import ApplicationError
from app.models import Asset, Episode, GenerationJob, Panel, Project, ProjectBible
from app.repository import Repository
from app.schemas import (
    AssetOut,
    BibleOut,
    EpisodeCreate,
    EpisodeOut,
    EpisodePatch,
    JobOut,
    Login,
    PanelCreate,
    PanelOut,
    PanelPatch,
    ProfileOut,
    ProjectCreate,
    ProjectOut,
    ProjectPatch,
    QuotaOut,
    SessionOut,
    Signup,
    UploadComplete,
    UploadRequest,
    UploadTicket,
)
from app.services import GenerationService, WorkspaceService

router = APIRouter(prefix="/api/v1")
Limit = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0)]


@router.get("/config", tags=["system"])
def public_config(settings: Config) -> dict[str, str | bool | int]:
    return {
        "auth_mode": settings.auth_mode,
        "mock_ai": settings.mock_ai,
        "phase": 1,
        "supabase_url": settings.supabase_url if settings.auth_mode == "supabase" else "",
        "supabase_anon_key": settings.supabase_anon_key if settings.auth_mode == "supabase" else "",
        "max_upload_bytes": settings.max_upload_bytes,
    }


@router.post("/auth/signup", response_model=SessionOut, status_code=201, tags=["auth"])
def signup(data: Signup, db: DB, settings: Config) -> SessionOut:
    return auth.signup(db, settings, data)


@router.post("/auth/login", response_model=SessionOut, tags=["auth"])
def login(data: Login, db: DB, settings: Config) -> SessionOut:
    return auth.login(db, settings, data)


@router.get("/auth/me", response_model=ProfileOut, tags=["auth"])
def me(user: User) -> ProfileOut:
    return ProfileOut.model_validate(user)


@router.post("/projects", response_model=ProjectOut, status_code=201, tags=["projects"])
def create_project(data: ProjectCreate, db: DB, user: User) -> Project:
    return WorkspaceService(db, user.id).create_project(data)


@router.get("/projects", response_model=list[ProjectOut], tags=["projects"])
def list_projects(db: DB, user: User, limit: Limit = 100, offset: Offset = 0) -> list[Project]:
    return list(
        db.scalars(
            select(Project)
            .where(Project.owner_id == user.id)
            .order_by(Project.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )


@router.get("/projects/{project_id}", response_model=ProjectOut, tags=["projects"])
def get_project(project_id: UUID, db: DB, user: User) -> Project:
    return Repository(db, user.id).project(project_id)


@router.patch("/projects/{project_id}", response_model=ProjectOut, tags=["projects"])
def update_project(project_id: UUID, data: ProjectPatch, db: DB, user: User) -> Project:
    return WorkspaceService(db, user.id).update_project(project_id, data)


@router.delete("/projects/{project_id}", status_code=204, tags=["projects"])
def delete_project(project_id: UUID, db: DB, user: User) -> None:
    WorkspaceService(db, user.id).delete_project(project_id)


@router.get("/projects/{project_id}/bible", response_model=BibleOut, tags=["projects"])
def get_bible(project_id: UUID, db: DB, user: User) -> ProjectBible:
    Repository(db, user.id).project(project_id)
    bible = db.scalar(select(ProjectBible).where(ProjectBible.project_id == project_id))
    if not bible:
        raise ApplicationError("Project Bible not found", "not_found", 404)
    return bible


@router.post(
    "/projects/{project_id}/episodes", response_model=EpisodeOut, status_code=201, tags=["episodes"]
)
def create_episode(project_id: UUID, data: EpisodeCreate, db: DB, user: User) -> Episode:
    return WorkspaceService(db, user.id).create_episode(project_id, data)


@router.get("/projects/{project_id}/episodes", response_model=list[EpisodeOut], tags=["episodes"])
def list_episodes(
    project_id: UUID, db: DB, user: User, limit: Limit = 100, offset: Offset = 0
) -> list[Episode]:
    Repository(db, user.id).project(project_id)
    return list(
        db.scalars(
            select(Episode)
            .where(Episode.project_id == project_id)
            .order_by(Episode.number)
            .limit(limit)
            .offset(offset)
        )
    )


@router.get("/episodes/{episode_id}", response_model=EpisodeOut, tags=["episodes"])
def get_episode(episode_id: UUID, db: DB, user: User) -> Episode:
    return Repository(db, user.id).episode(episode_id)


@router.patch("/episodes/{episode_id}", response_model=EpisodeOut, tags=["episodes"])
def update_episode(episode_id: UUID, data: EpisodePatch, db: DB, user: User) -> Episode:
    return WorkspaceService(db, user.id).update_episode(episode_id, data)


@router.delete("/episodes/{episode_id}", status_code=204, tags=["episodes"])
def delete_episode(episode_id: UUID, db: DB, user: User) -> None:
    WorkspaceService(db, user.id).delete_episode(episode_id)


@router.post(
    "/episodes/{episode_id}/panels", response_model=PanelOut, status_code=201, tags=["panels"]
)
def create_panel(episode_id: UUID, data: PanelCreate, db: DB, user: User) -> Panel:
    return WorkspaceService(db, user.id).create_panel(episode_id, data)


@router.get("/episodes/{episode_id}/panels", response_model=list[PanelOut], tags=["panels"])
def list_panels(
    episode_id: UUID, db: DB, user: User, limit: Limit = 200, offset: Offset = 0
) -> list[Panel]:
    Repository(db, user.id).episode(episode_id)
    return list(
        db.scalars(
            select(Panel)
            .where(Panel.episode_id == episode_id)
            .order_by(Panel.position)
            .limit(limit)
            .offset(offset)
        )
    )


@router.get("/panels/{panel_id}", response_model=PanelOut, tags=["panels"])
def get_panel(panel_id: UUID, db: DB, user: User) -> Panel:
    return Repository(db, user.id).panel(panel_id)


@router.patch("/panels/{panel_id}", response_model=PanelOut, tags=["panels"])
def update_panel(panel_id: UUID, data: PanelPatch, db: DB, user: User) -> Panel:
    return WorkspaceService(db, user.id).update_panel(panel_id, data)


@router.delete("/panels/{panel_id}", status_code=204, tags=["panels"])
def delete_panel(panel_id: UUID, db: DB, user: User) -> None:
    WorkspaceService(db, user.id).delete_panel(panel_id)


@router.post("/assets/upload-url", response_model=UploadTicket, status_code=201, tags=["assets"])
def upload_url(data: UploadRequest, db: DB, user: User, settings: Config) -> UploadTicket:
    return AssetService(db, settings).ticket(user.id, data)


@router.put("/assets/{asset_id}/upload", status_code=204, tags=["assets"])
async def upload(
    asset_id: UUID, token: str, request: Request, db: DB, settings: Config
) -> Response:
    # A scoped, expiring capability authenticates only this particular upload.
    if auth.verify_token(settings, token, "upload") != asset_id:
        raise ApplicationError("Invalid upload ticket", "unauthorized", 401)
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > settings.max_upload_bytes:
            raise ApplicationError("File is too large", "file_too_large", 413)
        content.extend(chunk)
    await run_in_threadpool(
        AssetService(db, settings).receive,
        asset_id,
        token,
        bytes(content),
        request.headers.get("content-type", ""),
    )
    return Response(status_code=204)


@router.post("/assets/complete", response_model=AssetOut, tags=["assets"])
def complete_upload(data: UploadComplete, db: DB, user: User, settings: Config) -> AssetOut:
    return AssetService(db, settings).complete(user.id, data.asset_id)


@router.get("/projects/{project_id}/assets", response_model=list[AssetOut], tags=["assets"])
def list_assets(
    project_id: UUID, db: DB, user: User, settings: Config, limit: Limit = 200, offset: Offset = 0
) -> list[AssetOut]:
    Repository(db, user.id).project(project_id)
    assets = db.scalars(
        select(Asset)
        .where(Asset.project_id == project_id, Asset.upload_status == "ready")
        .order_by(Asset.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    service = AssetService(db, settings)
    return [service.serialize(asset) for asset in assets]


@router.get("/assets/{asset_id}", response_model=AssetOut, tags=["assets"])
def get_asset(asset_id: UUID, db: DB, user: User, settings: Config) -> AssetOut:
    return AssetService(db, settings).serialize(Repository(db, user.id).asset(asset_id))


@router.get("/assets/{asset_id}/content", tags=["assets"])
def asset_content(asset_id: UUID, token: str, db: DB, settings: Config) -> Response:
    content, mime_type = AssetService(db, settings).content(asset_id, token)
    return Response(
        content=content,
        media_type=mime_type,
        headers={
            "Cache-Control": "private, max-age=300",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
        },
    )


@router.delete("/assets/{asset_id}", status_code=204, tags=["assets"])
def delete_asset(asset_id: UUID, db: DB, user: User, settings: Config) -> None:
    AssetService(db, settings).delete(user.id, asset_id)


@router.get("/jobs", response_model=list[JobOut], tags=["jobs"])
def list_jobs(db: DB, user: User, limit: Limit = 20, offset: Offset = 0) -> list[GenerationJob]:
    return list(
        db.scalars(
            select(GenerationJob)
            .where(GenerationJob.user_id == user.id)
            .order_by(GenerationJob.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )


@router.get("/quotas", response_model=QuotaOut, tags=["jobs"])
def get_quotas(db: DB, user: User, settings: Config) -> dict[str, object]:
    return GenerationService(db, user.id, settings).quotas()
