from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ApplicationError
from app.models import Asset, Character, Episode, GenerationJob, Panel, Project, Scene


class Repository:
    def __init__(self, db: Session, owner_id: UUID) -> None:
        self.db = db
        self.owner_id = owner_id

    def project(self, project_id: UUID, *, lock: bool = False) -> Project:
        query = select(Project).where(Project.id == project_id, Project.owner_id == self.owner_id)
        if lock:
            query = query.with_for_update()
        project = self.db.scalar(query)
        if not project:
            raise ApplicationError("Project not found", "not_found", 404)
        return project

    def episode(self, episode_id: UUID, *, lock: bool = False) -> Episode:
        query = (
            select(Episode)
            .join(Project)
            .where(Episode.id == episode_id, Project.owner_id == self.owner_id)
        )
        if lock:
            query = query.with_for_update(of=Episode)
        episode = self.db.scalar(query)
        if not episode:
            raise ApplicationError("Episode not found", "not_found", 404)
        return episode

    def panel(self, panel_id: UUID) -> Panel:
        panel = self.db.scalar(
            select(Panel)
            .join(Episode)
            .join(Project)
            .where(Panel.id == panel_id, Project.owner_id == self.owner_id)
        )
        if not panel:
            raise ApplicationError("Panel not found", "not_found", 404)
        return panel

    def scene(self, scene_id: UUID, *, lock: bool = False) -> Scene:
        query = (
            select(Scene)
            .join(Episode)
            .join(Project)
            .where(Scene.id == scene_id, Project.owner_id == self.owner_id)
        )
        if lock:
            query = query.with_for_update(of=Scene)
        scene = self.db.scalar(query)
        if not scene:
            raise ApplicationError("Scene not found", "not_found", 404)
        return scene

    def asset(self, asset_id: UUID, *, lock: bool = False) -> Asset:
        query = select(Asset).where(Asset.id == asset_id, Asset.owner_id == self.owner_id)
        if lock:
            query = query.with_for_update()
        asset = self.db.scalar(query)
        if not asset:
            raise ApplicationError("Asset not found", "not_found", 404)
        return asset

    def job(self, job_id: UUID, *, lock: bool = False) -> GenerationJob:
        query = select(GenerationJob).where(
            GenerationJob.id == job_id, GenerationJob.user_id == self.owner_id
        )
        if lock:
            query = query.with_for_update()
        job = self.db.scalar(query)
        if not job:
            raise ApplicationError("Generation job not found", "not_found", 404)
        return job

    def characters(self, project_id: UUID, character_ids: list[UUID]) -> list[Character]:
        self.project(project_id)
        if not character_ids:
            return []
        characters = list(
            self.db.scalars(
                select(Character).where(
                    Character.project_id == project_id,
                    Character.id.in_(character_ids),
                )
            )
        )
        by_id = {character.id: character for character in characters}
        if len(by_id) != len(character_ids):
            raise ApplicationError(
                "Every character must exist in this project", "invalid_character", 422
            )
        return [by_id[character_id] for character_id in character_ids]

    def list_characters(self, project_id: UUID, *, limit: int, offset: int) -> list[Character]:
        self.project(project_id)
        return list(
            self.db.scalars(
                select(Character)
                .join(Project)
                .where(Character.project_id == project_id, Project.owner_id == self.owner_id)
                .order_by(Character.name, Character.id)
                .limit(limit)
                .offset(offset)
            )
        )

    def image(self, asset_id: UUID, project_id: UUID) -> Asset:
        asset = self.asset(asset_id)
        if asset.project_id != project_id or asset.upload_status != "ready":
            raise ApplicationError(
                "Image must be ready and belong to this project", "invalid_asset"
            )
        if not asset.mime_type.startswith("image/"):
            raise ApplicationError("An image asset is required", "invalid_asset")
        return asset
