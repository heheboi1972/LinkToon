from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import ApplicationError
from app.image_generation import build_character_reference_input, build_scene_image_input
from app.models import Asset, Episode, GenerationJob, Panel, Profile, Project, ProjectBible, utcnow
from app.repository import Repository
from app.schemas import (
    EpisodeCreate,
    EpisodePatch,
    PanelCreate,
    PanelPatch,
    ProjectCreate,
    ProjectPatch,
    StoryGenerationRequest,
)
from app.video_generation import compose_scene_motion_prompt, scene_motion_input


class WorkspaceService:
    def __init__(self, db: Session, owner_id: UUID) -> None:
        self.db = db
        self.repo = Repository(db, owner_id)

    def create_project(self, data: ProjectCreate) -> Project:
        project = Project(owner_id=self.repo.owner_id, **data.model_dump(exclude={"visual_style"}))
        self.db.add(project)
        self.db.flush()
        self.db.add(
            ProjectBible(
                project_id=project.id,
                visual_bible={"preset": data.visual_style},
                story_bible={"idea": data.description},
            )
        )
        self.db.commit()
        return project

    def update_project(self, project_id: UUID, data: ProjectPatch) -> Project:
        project = self.repo.project(project_id)
        if data.thumbnail_asset_id:
            self.repo.image(data.thumbnail_asset_id, project_id)
        self.apply(project, data.model_dump(exclude_unset=True))
        self.db.commit()
        return project

    def create_episode(self, project_id: UUID, data: EpisodeCreate) -> Episode:
        project = self.repo.project(project_id, lock=True)
        number = (
            self.db.scalar(select(func.max(Episode.number)).where(Episode.project_id == project_id))
            or 0
        ) + 1
        episode = Episode(project_id=project_id, number=number, **data.model_dump())
        self.db.add(episode)
        project.updated_at = utcnow()
        self.db.commit()
        return episode

    def update_episode(self, episode_id: UUID, data: EpisodePatch) -> Episode:
        episode = self.repo.episode(episode_id)
        self.apply(episode, data.model_dump(exclude_unset=True))
        self.repo.project(episode.project_id).updated_at = utcnow()
        self.db.commit()
        return episode

    def create_panel(self, episode_id: UUID, data: PanelCreate) -> Panel:
        episode = self.repo.episode(episode_id, lock=True)
        if data.image_asset_id:
            self.repo.image(data.image_asset_id, episode.project_id)
        maximum = self.db.scalar(
            select(func.max(Panel.position)).where(Panel.episode_id == episode_id)
        )
        panel = Panel(
            episode_id=episode_id,
            position=(maximum + 1 if maximum is not None else 0),
            status="static" if data.image_asset_id else "empty",
            **data.model_dump(),
        )
        self.db.add(panel)
        self.touch(episode)
        self.db.commit()
        return panel

    def update_panel(self, panel_id: UUID, data: PanelPatch) -> Panel:
        panel = self.repo.panel(panel_id)
        episode = self.repo.episode(panel.episode_id)
        if data.image_asset_id:
            self.repo.image(data.image_asset_id, episode.project_id)
        self.apply(panel, data.model_dump(exclude_unset=True))
        if "image_asset_id" in data.model_fields_set:
            panel.status = "static" if data.image_asset_id else "empty"
        self.touch(episode)
        self.db.commit()
        return panel

    def delete_project(self, project_id: UUID) -> None:
        self.db.delete(self.repo.project(project_id))
        self.db.commit()

    def delete_episode(self, episode_id: UUID) -> None:
        episode = self.repo.episode(episode_id)
        self.repo.project(episode.project_id).updated_at = utcnow()
        self.db.delete(episode)
        self.db.commit()

    def delete_panel(self, panel_id: UUID) -> None:
        panel = self.repo.panel(panel_id)
        self.touch(self.repo.episode(panel.episode_id))
        self.db.delete(panel)
        self.db.commit()

    def touch(self, episode: Episode) -> None:
        episode.updated_at = utcnow()
        self.repo.project(episode.project_id).updated_at = utcnow()

    @staticmethod
    def apply(target: Project | Episode | Panel, changes: dict[str, Any]) -> None:
        for key, value in changes.items():
            setattr(target, key, value)


GenerationCategory = Literal["story", "image", "character", "video"]
QuotaCategory = Literal["story", "image", "motion"]
JobStatus = Literal[
    "queued", "running", "provider_pending", "saving", "succeeded", "failed", "canceled"
]

JOB_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "failed", "canceled"}),
    "running": frozenset({"provider_pending", "saving", "failed", "canceled"}),
    "provider_pending": frozenset({"saving", "failed", "canceled"}),
    "saving": frozenset({"succeeded", "failed", "canceled"}),
    "succeeded": frozenset(),
    "failed": frozenset(),
    "canceled": frozenset(),
}


class GenerationService:
    """Single trusted admission point for future provider-backed generation jobs."""

    def __init__(self, db: Session, owner_id: UUID, settings: Settings) -> None:
        self.db = db
        self.owner_id = owner_id
        self.settings = settings
        self.repo = Repository(db, owner_id)

    @staticmethod
    def window() -> tuple[datetime, datetime]:
        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)

    @staticmethod
    def quota_category(category: GenerationCategory) -> QuotaCategory:
        if category == "story":
            return "story"
        if category in {"image", "character"}:
            return "image"
        return "motion"

    def limit(self, category: QuotaCategory) -> int:
        return {
            "story": self.settings.story_daily_limit,
            "image": self.settings.image_daily_limit,
            "motion": self.settings.motion_daily_limit,
        }[category]

    def used(self, category: QuotaCategory, start: datetime, end: datetime) -> int:
        prefixes = {
            "story": ("story:%",),
            "image": ("image:%", "character:%"),
            "motion": ("video:%", "motion:%"),
        }[category]
        return int(
            self.db.scalar(
                select(func.count(GenerationJob.id)).where(
                    GenerationJob.user_id == self.owner_id,
                    or_(*(GenerationJob.job_type.like(prefix) for prefix in prefixes)),
                    GenerationJob.created_at >= start,
                    GenerationJob.created_at < end,
                )
            )
            or 0
        )

    def quotas(self) -> dict[str, Any]:
        start, end = self.window()
        buckets: dict[str, dict[str, int]] = {}
        categories: tuple[QuotaCategory, ...] = ("story", "image", "motion")
        for category in categories:
            maximum = self.limit(category)
            consumed = self.used(category, start, end)
            buckets[category] = {
                "limit": maximum,
                "used": consumed,
                "remaining": max(0, maximum - consumed),
            }
        return {"enabled": self.settings.ai_quotas_enabled, "reset_at": end, "buckets": buckets}

    def create_story_job(
        self,
        project_id: UUID,
        data: StoryGenerationRequest,
        idempotency_key: str,
    ) -> GenerationJob:
        project = self.repo.project(project_id)
        characters = self.repo.characters(project_id, data.characters)
        input_data: dict[str, Any] = {
            "idea": data.idea,
            "genre": data.genre or project.genre,
            "tone": data.tone,
            "theme": data.theme,
            "scene_count": data.scene_count,
            "characters": [
                {
                    "character_id": str(character.id),
                    "name": character.name,
                    "description": character.description,
                    "appearance": character.appearance,
                    "personality": character.personality,
                    "clothing": character.clothing,
                }
                for character in characters
            ],
        }
        use_mock = self.settings.mock_ai and self.settings.app_env != "production"
        return self.create_job(
            project_id,
            "story",
            "generate",
            input_data,
            idempotency_key,
            provider="mock" if use_mock else "openai",
            provider_model=(
                "mock-deterministic-v1" if use_mock else self.settings.openai_story_model
            ),
        )

    def create_scene_image_job(
        self,
        scene_id: UUID,
        idempotency_key: str,
    ) -> GenerationJob:
        # The row lock serializes admission for one Scene on PostgreSQL, preventing
        # two different clicks from creating simultaneous active image jobs.
        scene = self.repo.scene(scene_id, lock=True)
        episode = self.repo.episode(scene.episode_id)
        project = self.repo.project(episode.project_id)
        bible = self.db.scalar(select(ProjectBible).where(ProjectBible.project_id == project.id))
        script = scene.script if isinstance(scene.script, dict) else {}
        raw_character_ids = script.get("character_ids", [])
        character_ids: list[UUID] = []
        if isinstance(raw_character_ids, list):
            for value in raw_character_ids:
                if not isinstance(value, str):
                    continue
                try:
                    candidate = UUID(value)
                except ValueError:
                    continue
                if candidate not in character_ids:
                    character_ids.append(candidate)
        characters = self.repo.characters(project.id, character_ids)
        try:
            input_data = build_scene_image_input(scene, project, bible, characters)
        except ValueError as exc:
            raise ApplicationError(
                "Scene has no visual prompt for image generation",
                "scene_visual_prompt_missing",
                422,
            ) from exc
        # A stale pointer from a deleted/corrupt Asset must degrade to text-only
        # guidance instead of making the whole Scene job fail.
        reference_assets = input_data.get("reference_assets", [])
        valid_references: list[dict[str, str]] = []
        if isinstance(reference_assets, list):
            for item in reference_assets:
                if not isinstance(item, dict):
                    continue
                asset_value = item.get("asset_id")
                character_value = item.get("character_id")
                if not isinstance(asset_value, str) or not isinstance(character_value, str):
                    continue
                try:
                    asset_id = UUID(asset_value)
                except ValueError:
                    continue
                asset = self.db.scalar(
                    select(Asset).where(
                        Asset.id == asset_id,
                        Asset.owner_id == self.owner_id,
                        Asset.project_id == project.id,
                        Asset.asset_type == "image",
                        Asset.upload_status == "ready",
                    )
                )
                if asset is not None:
                    valid_references.append(
                        {"character_id": character_value, "asset_id": asset_value}
                    )
        input_data["reference_assets"] = valid_references
        input_data["reference_asset_ids"] = [item["asset_id"] for item in valid_references]
        use_mock = self.settings.mock_ai and self.settings.app_env != "production"
        image_provider = "mock" if use_mock else self.settings.image_provider
        if use_mock:
            image_model = "mock-deterministic-v1"
        elif image_provider == "fal":
            image_model = (
                self.settings.fal_reference_image_model
                if input_data.get("reference_asset_ids")
                else self.settings.fal_image_model
            )
        else:
            image_model = (
                self.settings.openai_image_reference_model
                if input_data.get("reference_asset_ids")
                else self.settings.openai_image_model
            )
        return self.create_job(
            project.id,
            "image",
            "scene",
            input_data,
            idempotency_key,
            provider=image_provider,
            provider_model=image_model,
            active_scope=("scene_id", str(scene.id)),
        )

    def create_scene_video_job(self, scene_id: UUID, idempotency_key: str) -> GenerationJob:
        scene = self.repo.scene(scene_id, lock=True)
        episode = self.repo.episode(scene.episode_id)
        project = self.repo.project(episode.project_id)
        if scene.image_asset_id is None:
            raise ApplicationError(
                "Generate a Scene image before creating motion", "scene_image_required", 409
            )
        image = self.db.scalar(
            select(Asset).where(
                Asset.id == scene.image_asset_id,
                Asset.owner_id == self.owner_id,
                Asset.project_id == project.id,
                Asset.asset_type == "image",
                Asset.upload_status == "ready",
            )
        )
        if image is None or image.mime_type not in {"image/png", "image/jpeg", "image/webp"}:
            raise ApplicationError(
                "Scene image is unavailable for motion generation", "scene_image_required", 409
            )
        if image.file_size > 5 * 1024 * 1024:
            raise ApplicationError(
                "Scene image is too large for motion generation", "scene_image_too_large", 413
            )
        if not image.width or not image.height:
            raise ApplicationError("Scene image dimensions are missing", "invalid_scene_image", 422)
        script = scene.script if isinstance(scene.script, dict) else {}
        raw_ids = script.get("character_ids", [])
        character_ids: list[UUID] = []
        if isinstance(raw_ids, list):
            for value in raw_ids:
                if isinstance(value, str):
                    try:
                        parsed = UUID(value)
                    except ValueError:
                        continue
                    if parsed not in character_ids:
                        character_ids.append(parsed)
        characters = self.repo.characters(project.id, character_ids)
        character_context = [
            ", ".join(
                part for part in (character.name, character.appearance, character.clothing) if part
            )[:240]
            for character in characters
        ]
        composed = compose_scene_motion_prompt(
            scene.id,
            script.get("narration"),
            script.get("visual_prompt"),
            raw_ids,
            width=image.width,
            height=image.height,
            duration_seconds=self.settings.runway_video_duration_seconds,
            character_context=character_context,
        )
        model = self.settings.runway_video_model
        use_mock = self.settings.mock_ai and self.settings.app_env != "production"
        input_data = scene_motion_input(
            scene_id=scene.id,
            episode_id=episode.id,
            image_asset_id=image.id,
            prompt=composed.prompt,
            width=image.width,
            height=image.height,
            model=model,
            duration_seconds=self.settings.runway_video_duration_seconds,
            ratio=composed.ratio,
        )
        return self.create_job(
            project.id,
            "video",
            "scene",
            input_data,
            idempotency_key,
            provider="mock" if use_mock else "runway",
            provider_model="mock-deterministic-v1" if use_mock else model,
            active_scope=("scene_id", str(scene.id)),
        )

    def create_character_reference_job(
        self, character_id: UUID, idempotency_key: str
    ) -> GenerationJob:
        from app.models import Character

        character = self.db.scalar(
            select(Character)
            .join(Project)
            .where(Character.id == character_id, Project.owner_id == self.owner_id)
            .with_for_update(of=Character)
        )
        if character is None:
            raise ApplicationError("Character not found", "not_found", 404)
        project = self.repo.project(character.project_id)
        bible = self.db.scalar(select(ProjectBible).where(ProjectBible.project_id == project.id))
        input_data = build_character_reference_input(character, project, bible)
        use_mock = self.settings.mock_ai and self.settings.app_env != "production"
        image_provider = "mock" if use_mock else self.settings.image_provider
        image_model = (
            "mock-deterministic-v1"
            if use_mock
            else (
                self.settings.fal_image_model
                if image_provider == "fal"
                else self.settings.openai_image_reference_model
            )
        )
        return self.create_job(
            project.id,
            "character",
            "reference",
            input_data,
            idempotency_key,
            provider=image_provider,
            provider_model=image_model,
            active_scope=("character_id", str(character.id)),
        )

    def create_job(
        self,
        project_id: UUID,
        category: GenerationCategory,
        action: str,
        input_data: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        provider: str | None = None,
        provider_model: str | None = None,
        active_scope: tuple[str, str] | None = None,
    ) -> GenerationJob:
        if not action or ":" in action or len(action) > 30:
            raise ApplicationError("Invalid generation action", "invalid_generation_action")
        normalized_key = idempotency_key.strip() if idempotency_key is not None else None
        if idempotency_key is not None and (not normalized_key or len(normalized_key) > 200):
            raise ApplicationError("Invalid idempotency key", "invalid_idempotency_key")
        selected_provider = provider
        if (
            selected_provider is None
            and self.settings.mock_ai
            and self.settings.app_env != "production"
        ):
            selected_provider = "mock"
        if selected_provider is None:
            raise ApplicationError(
                "No generation provider is configured", "provider_not_configured", 503
            )
        if selected_provider == "mock" and (
            not self.settings.mock_ai or self.settings.app_env == "production"
        ):
            raise ApplicationError(
                "Mock provider is disabled in this environment", "provider_not_configured", 503
            )
        # PostgreSQL serializes all quota admissions for one user on this row.
        self.db.scalar(select(Profile.id).where(Profile.id == self.owner_id).with_for_update())
        self.repo.project(project_id)
        job_type = f"{category}:{action}"
        job_input = input_data or {}
        if normalized_key:
            existing = self.db.scalar(
                select(GenerationJob).where(
                    GenerationJob.user_id == self.owner_id,
                    GenerationJob.idempotency_key == normalized_key,
                )
            )
            if existing:
                if (
                    existing.project_id == project_id
                    and existing.job_type == job_type
                    and existing.input == job_input
                ):
                    self.db.commit()
                    return existing
                raise ApplicationError(
                    "Idempotency key was already used for another request",
                    "idempotency_conflict",
                    409,
                )
        if active_scope is not None:
            field, value = active_scope
            active_jobs = self.db.scalars(
                select(GenerationJob).where(
                    GenerationJob.user_id == self.owner_id,
                    GenerationJob.project_id == project_id,
                    GenerationJob.job_type == job_type,
                    GenerationJob.status.in_(("queued", "running", "provider_pending", "saving")),
                )
            )
            if any(
                isinstance(candidate.input, dict) and candidate.input.get(field) == value
                for candidate in active_jobs
            ):
                active_code = (
                    "scene_image_job_active"
                    if job_type == "image:scene"
                    else (
                        "scene_video_job_active"
                        if job_type == "video:scene"
                        else "character_reference_job_active"
                    )
                )
                raise ApplicationError(
                    "A generation job is already active for this resource",
                    active_code,
                    409,
                )
        start, end = self.window()
        quota_category = self.quota_category(category)
        maximum = self.limit(quota_category)
        if self.settings.ai_quotas_enabled and self.used(quota_category, start, end) >= maximum:
            raise ApplicationError(
                f"Daily {quota_category} generation limit reached",
                "generation_quota_exceeded",
                429,
            )
        job = GenerationJob(
            user_id=self.owner_id,
            project_id=project_id,
            job_type=job_type,
            input=job_input,
            idempotency_key=normalized_key,
            provider=selected_provider,
            provider_model=provider_model,
        )
        self.db.add(job)
        self.db.commit()
        return job

    def transition(
        self, job_id: UUID, status: JobStatus, *, progress: int | None = None
    ) -> GenerationJob:
        job = self.repo.job(job_id, lock=True)
        if status not in JOB_TRANSITIONS.get(job.status, frozenset()):
            raise ApplicationError(
                f"Cannot change job status from {job.status} to {status}",
                "invalid_job_transition",
                409,
            )
        if progress is not None and not 0 <= progress <= 100:
            raise ApplicationError("Job progress must be between 0 and 100", "invalid_progress")
        now = utcnow()
        job.status = status
        if progress is not None:
            job.progress = progress
        if status == "running" and job.started_at is None:
            job.started_at = now
        if status in {"succeeded", "failed", "canceled"}:
            job.completed_at = now
            if status == "succeeded":
                job.progress = 100
        self.db.commit()
        return job

    def cancel(self, job_id: UUID) -> GenerationJob:
        job = self.repo.job(job_id, lock=True)
        if job.status == "canceled":
            return job
        if job.status in {"succeeded", "failed"}:
            raise ApplicationError("Completed jobs cannot be canceled", "job_not_cancelable", 409)
        job.cancel_requested_at = utcnow()
        job.status = "canceled"
        job.completed_at = job.cancel_requested_at
        job.next_poll_at = job.cancel_requested_at if job.provider_task_id else None
        self.db.commit()
        return job
