"""V1 relational foundation; later-phase tables have no public mutation API yet."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


class Identity:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Updated:
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Profile(Identity, Updated, Base):
    __tablename__ = "profiles"
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str | None] = mapped_column(String(256))


class Project(Identity, Updated, Base):
    __tablename__ = "projects"
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(default="")
    genre: Mapped[str] = mapped_column(String(50), default="fantasy")
    orientation: Mapped[str] = mapped_column(String(20), default="vertical")
    creation_mode: Mapped[str] = mapped_column(String(20), default="manual")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    thumbnail_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("assets.id", name="fk_projects_thumbnail", use_alter=True, ondelete="SET NULL")
    )
    __table_args__ = (
        CheckConstraint("orientation IN ('vertical','horizontal')", name="ck_project_orientation"),
        CheckConstraint(
            "creation_mode IN ('manual','assisted','ai_first')", name="ck_creation_mode"
        ),
        CheckConstraint("status IN ('draft','active','archived')", name="ck_project_status"),
        Index("ix_projects_owner_updated", "owner_id", "updated_at"),
    )


class ProjectBible(Identity, Updated, Base):
    __tablename__ = "project_bibles"
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True
    )
    story_bible: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    world_bible: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    visual_bible: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    prompt_rules: Mapped[list[str]] = mapped_column(JSONType, default=list)
    negative_rules: Mapped[list[str]] = mapped_column(JSONType, default=list)


class Asset(Identity, Base):
    __tablename__ = "assets"
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    asset_type: Mapped[str] = mapped_column(String(20))
    mime_type: Mapped[str] = mapped_column(String(100))
    storage_provider: Mapped[str] = mapped_column(String(20))
    storage_bucket: Mapped[str | None] = mapped_column(String(100))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    source: Mapped[str] = mapped_column(String(20), default="upload")
    provider: Mapped[str | None] = mapped_column(String(40))
    provider_task_id: Mapped[str | None] = mapped_column(String(200))
    generation_job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("generation_jobs.id", ondelete="SET NULL"), index=True
    )
    prompt: Mapped[str | None]
    public_url: Mapped[str | None]
    thumbnail_url: Mapped[str | None]
    width: Mapped[int | None]
    height: Mapped[int | None]
    duration_ms: Mapped[int | None]
    file_size: Mapped[int]
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    upload_status: Mapped[str] = mapped_column(String(20), default="pending")
    __table_args__ = (
        CheckConstraint("file_size > 0", name="ck_asset_size"),
        CheckConstraint("upload_status IN ('pending','uploaded','ready')", name="ck_asset_upload"),
        CheckConstraint("source IN ('upload','generated')", name="ck_asset_source"),
        CheckConstraint(
            "asset_type IN ('image','video','audio','mask','thumbnail','reference','export')",
            name="ck_asset_type",
        ),
    )


class Character(Identity, Updated, Base):
    __tablename__ = "characters"
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(default="")
    appearance: Mapped[str] = mapped_column(default="")
    personality: Mapped[str] = mapped_column(default="")
    clothing: Mapped[str] = mapped_column(default="")
    prompt_token: Mapped[str] = mapped_column(String(100), default="")
    primary_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL")
    )
    character_bible: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    appearance_lock_json: Mapped[dict[str, Any]] = mapped_column(
        "appearance_lock", JSONType, default=dict
    )
    style_lock_json: Mapped[dict[str, Any]] = mapped_column("style_lock", JSONType, default=dict)
    reference_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("assets.id", name="fk_characters_reference_asset", ondelete="SET NULL"),
        index=True,
    )
    character_revision: Mapped[int] = mapped_column(default=1)
    reference_generated_from_revision: Mapped[int | None]
    reference_stale: Mapped[bool] = mapped_column(default=False)


class CharacterReference(Identity, Base):
    __tablename__ = "character_references"
    character_id: Mapped[UUID] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    asset_id: Mapped[UUID] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"))
    reference_type: Mapped[str] = mapped_column(String(20))
    __table_args__ = (
        CheckConstraint(
            "reference_type IN ('face','upper_body','full_body','pose','expression','outfit')",
            name="ck_reference_type",
        ),
    )


class Episode(Identity, Updated, Base):
    __tablename__ = "episodes"
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int]
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    __table_args__ = (
        UniqueConstraint("project_id", "number", name="uq_episode_number"),
        CheckConstraint("number > 0", name="ck_episode_number"),
        CheckConstraint(
            "status IN ('draft','public','unlisted','private')", name="ck_episode_status"
        ),
    )


class Scene(Identity, Updated, Base):
    __tablename__ = "scenes"
    episode_id: Mapped[UUID] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(default=0)
    title: Mapped[str] = mapped_column(String(120), default="")
    script: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    image_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL"), index=True
    )
    video_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("assets.id", name="fk_scenes_video_asset", ondelete="SET NULL"), index=True
    )


class Panel(Identity, Updated, Base):
    __tablename__ = "panels"
    episode_id: Mapped[UUID] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE"), index=True
    )
    scene_id: Mapped[UUID | None] = mapped_column(ForeignKey("scenes.id", ondelete="SET NULL"))
    position: Mapped[int]
    title: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(default="")
    dialogue: Mapped[str] = mapped_column(default="")
    status: Mapped[str] = mapped_column(String(20), default="empty")
    image_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL")
    )
    script: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    __table_args__ = (
        UniqueConstraint("episode_id", "position", name="uq_panel_position"),
        CheckConstraint("position >= 0", name="ck_panel_position"),
        CheckConstraint(
            "status IN ('empty','static','generating','animated')", name="ck_panel_status"
        ),
    )


class GenerationJob(Identity, Updated, Base):
    __tablename__ = "generation_jobs"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    job_type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    provider: Mapped[str | None] = mapped_column(String(40))
    provider_model: Mapped[str | None] = mapped_column(String(200))
    provider_task_id: Mapped[str | None] = mapped_column(String(200), index=True)
    input: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    output: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    provider_output: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    progress: Mapped[int] = mapped_column(default=0)
    retry_count: Mapped[int] = mapped_column(default=0)
    next_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(200))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(100))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    cost_estimate: Mapped[float | None]
    cost_actual: Mapped[float | None]
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None]
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("progress BETWEEN 0 AND 100", name="ck_job_progress"),
        CheckConstraint("retry_count >= 0", name="ck_job_retry_count"),
        CheckConstraint(
            "status IN ('queued','running','provider_pending','saving','succeeded','failed',"
            "'canceled')",
            name="ck_job_status",
        ),
        UniqueConstraint("user_id", "idempotency_key", name="uq_jobs_user_idempotency"),
        Index("ix_jobs_user_created", "user_id", "created_at"),
        Index("ix_jobs_status_poll", "status", "next_poll_at"),
    )


class MotionPlan(Identity, Base):
    __tablename__ = "motion_plans"
    panel_id: Mapped[UUID] = mapped_column(ForeignKey("panels.id", ondelete="CASCADE"), index=True)
    mode: Mapped[str] = mapped_column(String(30))
    analysis: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    plan: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    version: Mapped[int] = mapped_column(default=1)
    __table_args__ = (
        UniqueConstraint("panel_id", "version", name="uq_motion_plan_version"),
        CheckConstraint(
            "mode IN ('exact','partial_generate','full_generate','first_last')",
            name="ck_motion_mode",
        ),
    )


class MotionLayer(Identity, Base):
    __tablename__ = "motion_layers"
    panel_id: Mapped[UUID] = mapped_column(ForeignKey("panels.id", ondelete="CASCADE"), index=True)
    layer_type: Mapped[str] = mapped_column(String(30))
    mask_asset_id: Mapped[UUID | None] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"))
    locked: Mapped[bool] = mapped_column(default=False)
    z_index: Mapped[int] = mapped_column(default=0)
    motion_config: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class Animation(Identity, Base):
    __tablename__ = "animations"
    panel_id: Mapped[UUID] = mapped_column(ForeignKey("panels.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("generation_jobs.id", ondelete="SET NULL")
    )
    webm_asset_id: Mapped[UUID | None] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"))
    mp4_asset_id: Mapped[UUID | None] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"))
    poster_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL")
    )
    duration_ms: Mapped[int]
    version: Mapped[int] = mapped_column(default=1)


class PublishVersion(Identity, Base):
    __tablename__ = "publish_versions"
    episode_id: Mapped[UUID] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int]
    slug: Mapped[str] = mapped_column(String(160), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONType)
    __table_args__ = (
        UniqueConstraint("episode_id", "version", name="uq_publish_version"),
        CheckConstraint(
            "status IN ('draft','public','unlisted','private')", name="ck_publish_status"
        ),
    )


class Publication(Identity, Updated, Base):
    __tablename__ = "publications"
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    episode_id: Mapped[UUID] = mapped_column(ForeignKey("episodes.id", ondelete="CASCADE"))
    slug: Mapped[str] = mapped_column(String(160), unique=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(default="")
    visibility: Mapped[str] = mapped_column(String(20), default="public")
    status: Mapped[str] = mapped_column(String(20), default="published")
    current_version: Mapped[int] = mapped_column(default=1)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("episode_id", name="uq_publication_episode"),
        CheckConstraint(
            "visibility IN ('private','unlisted','public')", name="ck_publication_visibility"
        ),
        CheckConstraint("status IN ('published','unpublished')", name="ck_publication_status"),
        CheckConstraint("current_version > 0", name="ck_publication_version"),
        Index("ix_publications_project_status", "project_id", "status"),
    )


class PublicationSnapshot(Identity, Base):
    __tablename__ = "publication_snapshots"
    publication_id: Mapped[UUID] = mapped_column(
        ForeignKey("publications.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int]
    episode_title: Mapped[str] = mapped_column(String(120))
    episode_description: Mapped[str] = mapped_column(default="")
    __table_args__ = (
        UniqueConstraint("publication_id", "version", name="uq_publication_snapshot"),
    )


class PublicationScene(Identity, Base):
    __tablename__ = "publication_scenes"
    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("publication_snapshots.id", ondelete="CASCADE"), index=True
    )
    source_scene_id: Mapped[UUID]
    position: Mapped[int]
    title: Mapped[str] = mapped_column(String(120), default="")
    narration: Mapped[str] = mapped_column(default="")
    dialogue: Mapped[list[dict[str, str]]] = mapped_column(JSONType, default=list)
    image_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), index=True
    )
    video_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), index=True
    )
    __table_args__ = (
        UniqueConstraint("snapshot_id", "position", name="uq_publication_scene_position"),
        CheckConstraint("position >= 0", name="ck_publication_scene_position"),
    )
