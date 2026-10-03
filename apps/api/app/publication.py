import re
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.assets import AssetService
from app.auth import sign_token, verify_token
from app.config import Settings
from app.errors import ApplicationError
from app.models import (
    Asset,
    Character,
    Episode,
    Profile,
    Publication,
    PublicationScene,
    PublicationSnapshot,
    Scene,
    utcnow,
)
from app.repository import Repository
from app.schemas import (
    ProjectOverviewOut,
    PublicationCreate,
    PublicationOut,
    PublicationPatch,
    PublicationReaderOut,
    PublicationSceneOut,
    ReaderDialogueOut,
)


class PublicationService:
    def __init__(self, db: Session, owner_id: UUID | None, settings: Settings) -> None:
        self.db = db
        self.owner_id = owner_id
        self.settings = settings

    def publish(self, episode_id: UUID, data: PublicationCreate) -> PublicationOut:
        episode = self._repository().episode(episode_id, lock=True)
        existing = self.db.scalar(select(Publication).where(Publication.episode_id == episode.id))
        if existing:
            if existing.status == "published":
                return self.serialize(existing)
            raise ApplicationError(
                "This episode already has a publication. Use republish to make it public again.",
                "publication_exists",
                409,
            )
        scenes = self._episode_scenes(episode.id)
        self._require_scenes(scenes)
        slug_title = re.sub(r"[^a-z0-9]+", "-", episode.title.lower()).strip("-")[:48]
        slug = f"{slug_title or f'episode-{episode.number}'}-{uuid4().hex[:8]}"
        publication = Publication(
            owner_id=self._owner_id(),
            project_id=episode.project_id,
            episode_id=episode.id,
            slug=slug,
            title=data.title or episode.title,
            description=data.description if data.description is not None else episode.description,
            visibility=data.visibility,
            status="published",
            current_version=1,
            published_at=utcnow(),
        )
        self.db.add(publication)
        self.db.flush()
        self._append_snapshot(publication, episode, scenes, 1)
        self._repository().project(episode.project_id).updated_at = utcnow()
        self.db.commit()
        return self.serialize(publication)

    def for_episode(self, episode_id: UUID) -> PublicationOut:
        self._repository().episode(episode_id)
        publication = self.db.scalar(
            select(Publication).where(
                Publication.episode_id == episode_id, Publication.owner_id == self._owner_id()
            )
        )
        if not publication:
            raise ApplicationError("Publication not found", "not_found", 404)
        return self.serialize(publication)

    def update(self, publication_id: UUID, data: PublicationPatch) -> PublicationOut:
        publication = self._owned(publication_id, lock=True)
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(publication, key, value)
        publication.updated_at = utcnow()
        self.db.commit()
        return self.serialize(publication)

    def unpublish(self, publication_id: UUID) -> PublicationOut:
        publication = self._owned(publication_id, lock=True)
        publication.status = "unpublished"
        publication.updated_at = utcnow()
        self.db.commit()
        return self.serialize(publication)

    def republish(self, publication_id: UUID) -> PublicationOut:
        publication = self._owned(publication_id, lock=True)
        episode = self._repository().episode(publication.episode_id)
        scenes = self._episode_scenes(episode.id)
        self._require_scenes(scenes)
        next_version = publication.current_version + 1
        self._append_snapshot(publication, episode, scenes, next_version)
        publication.current_version = next_version
        publication.status = "published"
        publication.published_at = utcnow()
        publication.updated_at = utcnow()
        self._repository().project(episode.project_id).updated_at = utcnow()
        self.db.commit()
        return self.serialize(publication)

    def public_reader(self, slug: str) -> PublicationReaderOut:
        publication = self._visible(slug)
        snapshot = self._current_snapshot(publication)
        rows = self._snapshot_scenes(snapshot.id)
        asset_ids = {
            asset_id
            for row in rows
            for asset_id in (row.image_asset_id, row.video_asset_id)
            if asset_id is not None
        }
        assets = (
            list(
                self.db.scalars(
                    select(Asset).where(
                        Asset.id.in_(asset_ids),
                        Asset.owner_id == publication.owner_id,
                        Asset.project_id == publication.project_id,
                        Asset.upload_status == "ready",
                    )
                )
            )
            if asset_ids
            else []
        )
        by_id = {asset.id: asset for asset in assets}
        author = self.db.get(Profile, publication.owner_id)
        return PublicationReaderOut(
            slug=publication.slug,
            title=publication.title,
            description=publication.description,
            author_name=author.display_name if author else "LinkToon Creator",
            visibility=publication.visibility,
            published_at=publication.published_at or publication.created_at,
            scene_count=len(rows),
            scenes=[self._public_scene(publication, row, by_id) for row in rows],
        )

    def public_media(
        self, slug: str, asset_id: UUID, token: str, range_header: str | None
    ) -> tuple[bytes, str, int, dict[str, str]]:
        publication = self._visible(slug)
        purpose = self._media_purpose(publication.id, publication.current_version)
        if verify_token(self.settings, token, purpose) != asset_id:
            raise ApplicationError("Invalid publication media token", "unauthorized", 401)
        snapshot = self._current_snapshot(publication)
        referenced = self.db.scalar(
            select(PublicationScene.id).where(
                PublicationScene.snapshot_id == snapshot.id,
                (PublicationScene.image_asset_id == asset_id)
                | (PublicationScene.video_asset_id == asset_id),
            )
        )
        if not referenced:
            raise ApplicationError("Publication media not found", "not_found", 404)
        return AssetService(self.db, self.settings).read_media(asset_id, range_header)

    def overview(self, project_id: UUID) -> ProjectOverviewOut:
        project = self._repository().project(project_id)
        episode_filter = Episode.project_id == project.id
        episode_count = self.db.scalar(select(func.count(Episode.id)).where(episode_filter)) or 0
        scene_count = (
            self.db.scalar(select(func.count(Scene.id)).join(Episode).where(episode_filter)) or 0
        )
        image_count = (
            self.db.scalar(
                select(func.count(Scene.id))
                .join(Episode)
                .join(Asset, Asset.id == Scene.image_asset_id)
                .where(episode_filter, Asset.upload_status == "ready", Asset.asset_type == "image")
            )
            or 0
        )
        motion_count = (
            self.db.scalar(
                select(func.count(Scene.id))
                .join(Episode)
                .join(Asset, Asset.id == Scene.video_asset_id)
                .where(episode_filter, Asset.upload_status == "ready", Asset.asset_type == "video")
            )
            or 0
        )
        character_count = (
            self.db.scalar(
                select(func.count(Character.id)).where(Character.project_id == project.id)
            )
            or 0
        )
        reference_count = (
            self.db.scalar(
                select(func.count(Character.id))
                .join(Asset, Asset.id == Character.reference_asset_id)
                .where(
                    Character.project_id == project.id,
                    Character.reference_stale.is_(False),
                    Asset.upload_status == "ready",
                )
            )
            or 0
        )
        published_count = (
            self.db.scalar(
                select(func.count(Publication.id)).where(
                    Publication.project_id == project.id, Publication.status == "published"
                )
            )
            or 0
        )
        latest = self.db.execute(
            select(Scene, Asset)
            .join(Asset, Scene.image_asset_id == Asset.id)
            .join(Episode, Episode.id == Scene.episode_id)
            .where(
                Episode.project_id == project.id,
                Asset.owner_id == self._owner_id(),
                Asset.upload_status == "ready",
                Asset.asset_type == "image",
            )
            .order_by(Scene.updated_at.desc(), Scene.id.desc())
            .limit(1)
        ).first()
        latest_title = None
        image_url = None
        if latest:
            latest_scene, latest_asset = latest
            latest_title = latest_scene.title
            image_url = AssetService(self.db, self.settings).serialize(latest_asset).public_url
        return ProjectOverviewOut(
            project_id=project.id,
            episode_count=episode_count,
            scene_count=scene_count,
            image_count=image_count,
            motion_count=motion_count,
            character_count=character_count,
            character_reference_count=reference_count,
            published_count=published_count,
            latest_scene_image_url=image_url,
            latest_scene_title=latest_title,
            updated_at=project.updated_at,
        )

    def serialize(self, publication: Publication) -> PublicationOut:
        snapshot = self.db.scalar(
            select(PublicationSnapshot).where(
                PublicationSnapshot.publication_id == publication.id,
                PublicationSnapshot.version == publication.current_version,
            )
        )
        rows = self._snapshot_scenes(snapshot.id) if snapshot else []
        return PublicationOut(
            id=publication.id,
            project_id=publication.project_id,
            episode_id=publication.episode_id,
            slug=publication.slug,
            title=publication.title,
            description=publication.description,
            visibility=publication.visibility,
            status=publication.status,
            current_version=publication.current_version,
            published_at=publication.published_at,
            scene_count=len(rows),
            image_count=sum(row.image_asset_id is not None for row in rows),
            motion_count=sum(row.video_asset_id is not None for row in rows),
        )

    def _append_snapshot(
        self,
        publication: Publication,
        episode: Episode,
        scenes: list[Scene],
        version: int,
    ) -> None:
        snapshot = PublicationSnapshot(
            publication_id=publication.id,
            version=version,
            episode_title=episode.title,
            episode_description=episode.description,
        )
        self.db.add(snapshot)
        self.db.flush()
        asset_ids = {
            asset_id
            for scene in scenes
            for asset_id in (scene.image_asset_id, scene.video_asset_id)
            if asset_id is not None
        }
        assets = (
            list(
                self.db.scalars(
                    select(Asset).where(
                        Asset.id.in_(asset_ids),
                        Asset.owner_id == self._owner_id(),
                        Asset.project_id == publication.project_id,
                        Asset.upload_status == "ready",
                    )
                )
            )
            if asset_ids
            else []
        )
        by_id = {asset.id: asset for asset in assets}
        for scene in scenes:
            script = scene.script if isinstance(scene.script, dict) else {}
            image = by_id.get(scene.image_asset_id) if scene.image_asset_id else None
            video = by_id.get(scene.video_asset_id) if scene.video_asset_id else None
            dialogue = self._dialogue(script.get("dialogue"))
            self.db.add(
                PublicationScene(
                    snapshot_id=snapshot.id,
                    source_scene_id=scene.id,
                    position=scene.position,
                    title=scene.title,
                    narration=(
                        script.get("narration") if isinstance(script.get("narration"), str) else ""
                    ),
                    dialogue=dialogue,
                    image_asset_id=(image.id if image and image.asset_type == "image" else None),
                    video_asset_id=(video.id if video and video.asset_type == "video" else None),
                )
            )

    def _public_scene(
        self,
        publication: Publication,
        scene: PublicationScene,
        assets: dict[UUID, Asset],
    ) -> PublicationSceneOut:
        return PublicationSceneOut(
            order=scene.position + 1,
            title=scene.title,
            narration=scene.narration,
            dialogue=[ReaderDialogueOut.model_validate(line) for line in scene.dialogue],
            image_url=self._media_url(publication, scene.image_asset_id, assets),
            video_url=self._media_url(publication, scene.video_asset_id, assets),
        )

    def _media_url(
        self,
        publication: Publication,
        asset_id: UUID | None,
        assets: dict[UUID, Asset],
    ) -> str | None:
        if not asset_id or asset_id not in assets:
            return None
        purpose = self._media_purpose(publication.id, publication.current_version)
        token = sign_token(self.settings, asset_id, purpose, minutes=15)
        return (
            f"{self.settings.api_public_url}/api/v1/publications/{publication.slug}"
            f"/assets/{asset_id}/content?token={token}"
        )

    @staticmethod
    def _dialogue(value: object) -> list[dict[str, str]]:
        output: list[dict[str, str]] = []
        if isinstance(value, list):
            for line in value:
                if not isinstance(line, dict):
                    continue
                character = line.get("character")
                text = line.get("text")
                if isinstance(character, str) and isinstance(text, str) and text.strip():
                    output.append({"character": character.strip(), "text": text.strip()})
        return output

    def _episode_scenes(self, episode_id: UUID) -> list[Scene]:
        return list(
            self.db.scalars(
                select(Scene)
                .where(Scene.episode_id == episode_id)
                .order_by(Scene.position, Scene.id)
            )
        )

    @staticmethod
    def _require_scenes(scenes: list[Scene]) -> None:
        if not scenes:
            raise ApplicationError("Add at least one scene before publishing", "empty_episode", 422)

    def _owned(self, publication_id: UUID, *, lock: bool = False) -> Publication:
        owner_id = self._owner_id()
        query = select(Publication).where(
            Publication.id == publication_id, Publication.owner_id == owner_id
        )
        if lock:
            query = query.with_for_update()
        publication = self.db.scalar(query)
        if not publication:
            raise ApplicationError("Publication not found", "not_found", 404)
        return publication

    def _owner_id(self) -> UUID:
        if self.owner_id is None:
            raise ApplicationError("Sign in to continue", "unauthorized", 401)
        return self.owner_id

    def _repository(self) -> Repository:
        return Repository(self.db, self._owner_id())

    def _visible(self, slug: str) -> Publication:
        publication = self.db.scalar(
            select(Publication).where(
                Publication.slug == slug,
                Publication.status == "published",
                Publication.visibility.in_(("public", "unlisted")),
            )
        )
        if not publication:
            raise ApplicationError("Publication not found", "not_found", 404)
        return publication

    def _current_snapshot(self, publication: Publication) -> PublicationSnapshot:
        snapshot = self.db.scalar(
            select(PublicationSnapshot).where(
                PublicationSnapshot.publication_id == publication.id,
                PublicationSnapshot.version == publication.current_version,
            )
        )
        if not snapshot:
            raise ApplicationError("Publication snapshot not found", "not_found", 404)
        return snapshot

    def _snapshot_scenes(self, snapshot_id: UUID) -> list[PublicationScene]:
        return list(
            self.db.scalars(
                select(PublicationScene)
                .where(PublicationScene.snapshot_id == snapshot_id)
                .order_by(PublicationScene.position, PublicationScene.id)
            )
        )

    @staticmethod
    def _media_purpose(publication_id: UUID, version: int) -> str:
        return f"publication-media:{publication_id}:{version}"
