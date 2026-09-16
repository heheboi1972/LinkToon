from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import ApplicationError
from app.models import Episode, GenerationJob, Panel, Profile, Project, ProjectBible, utcnow
from app.repository import Repository
from app.schemas import (
    EpisodeCreate,
    EpisodePatch,
    PanelCreate,
    PanelPatch,
    ProjectCreate,
    ProjectPatch,
)


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


GenerationCategory = Literal["story", "image", "motion"]


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

    def limit(self, category: GenerationCategory) -> int:
        return {
            "story": self.settings.story_daily_limit,
            "image": self.settings.image_daily_limit,
            "motion": self.settings.motion_daily_limit,
        }[category]

    def used(self, category: GenerationCategory, start: datetime, end: datetime) -> int:
        return int(
            self.db.scalar(
                select(func.count(GenerationJob.id)).where(
                    GenerationJob.user_id == self.owner_id,
                    GenerationJob.job_type.like(f"{category}:%"),
                    GenerationJob.created_at >= start,
                    GenerationJob.created_at < end,
                )
            )
            or 0
        )

    def quotas(self) -> dict[str, Any]:
        start, end = self.window()
        buckets: dict[str, dict[str, int]] = {}
        categories: tuple[GenerationCategory, ...] = ("story", "image", "motion")
        for category in categories:
            maximum = self.limit(category)
            consumed = self.used(category, start, end)
            buckets[category] = {
                "limit": maximum,
                "used": consumed,
                "remaining": max(0, maximum - consumed),
            }
        return {"enabled": self.settings.ai_quotas_enabled, "reset_at": end, "buckets": buckets}

    def create_job(
        self,
        project_id: UUID,
        category: GenerationCategory,
        action: str,
        input_data: dict[str, Any] | None = None,
    ) -> GenerationJob:
        if not action or ":" in action or len(action) > 30:
            raise ApplicationError("Invalid generation action", "invalid_generation_action")
        # PostgreSQL serializes all quota admissions for one user on this row.
        self.db.scalar(select(Profile.id).where(Profile.id == self.owner_id).with_for_update())
        self.repo.project(project_id)
        start, end = self.window()
        maximum = self.limit(category)
        if self.settings.ai_quotas_enabled and self.used(category, start, end) >= maximum:
            raise ApplicationError(
                f"Daily {category} generation limit reached",
                "generation_quota_exceeded",
                429,
            )
        job = GenerationJob(
            user_id=self.owner_id,
            project_id=project_id,
            job_type=f"{category}:{action}",
            input=input_data or {},
        )
        self.db.add(job)
        self.db.commit()
        return job
