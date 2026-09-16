from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ApplicationError
from app.models import Asset, Episode, Panel, Project


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

    def asset(self, asset_id: UUID, *, lock: bool = False) -> Asset:
        query = select(Asset).where(Asset.id == asset_id, Asset.owner_id == self.owner_id)
        if lock:
            query = query.with_for_update()
        asset = self.db.scalar(query)
        if not asset:
            raise ApplicationError("Asset not found", "not_found", 404)
        return asset

    def image(self, asset_id: UUID, project_id: UUID) -> Asset:
        asset = self.asset(asset_id)
        if asset.project_id != project_id or asset.upload_status != "ready":
            raise ApplicationError(
                "Image must be ready and belong to this project", "invalid_asset"
            )
        if not asset.mime_type.startswith("image/"):
            raise ApplicationError("An image asset is required", "invalid_asset")
        return asset
