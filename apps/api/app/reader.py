from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assets import AssetService
from app.config import Settings
from app.models import Asset, Scene
from app.repository import Repository
from app.schemas import EpisodeReaderOut, ReaderDialogueOut, ReaderSceneOut


class ReaderService:
    def __init__(self, db: Session, owner_id: UUID, settings: Settings) -> None:
        self.db = db
        self.owner_id = owner_id
        self.settings = settings
        self.repository = Repository(db, owner_id)
        self.assets = AssetService(db, settings)

    def episode(self, episode_id: UUID) -> EpisodeReaderOut:
        episode = self.repository.episode(episode_id)
        scenes = list(
            self.db.scalars(
                select(Scene)
                .where(Scene.episode_id == episode.id)
                .order_by(Scene.position, Scene.id)
            )
        )
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
                        Asset.owner_id == self.owner_id,
                        Asset.project_id == episode.project_id,
                        Asset.upload_status == "ready",
                    )
                )
            )
            if asset_ids
            else []
        )
        by_id = {asset.id: asset for asset in assets}

        return EpisodeReaderOut(
            episode_id=episode.id,
            project_id=episode.project_id,
            number=episode.number,
            title=episode.title,
            summary=episode.description,
            scenes=[self._scene(scene, index + 1, by_id) for index, scene in enumerate(scenes)],
        )

    def _scene(self, scene: Scene, order: int, assets: dict[UUID, Asset]) -> ReaderSceneOut:
        script = scene.script if isinstance(scene.script, dict) else {}
        raw_dialogue = script.get("dialogue")
        dialogue: list[ReaderDialogueOut] = []
        if isinstance(raw_dialogue, list):
            for line in raw_dialogue:
                if not isinstance(line, dict):
                    continue
                character = line.get("character")
                text = line.get("text")
                if isinstance(character, str) and isinstance(text, str) and text.strip():
                    dialogue.append(
                        ReaderDialogueOut(character=character.strip(), text=text.strip())
                    )

        image = assets.get(scene.image_asset_id) if scene.image_asset_id else None
        video = assets.get(scene.video_asset_id) if scene.video_asset_id else None
        narration = script.get("narration", "")
        return ReaderSceneOut(
            id=scene.id,
            order=order,
            title=scene.title,
            narration=narration if isinstance(narration, str) else "",
            dialogue=dialogue,
            image_url=(
                self.assets.serialize(image).public_url
                if image is not None and image.asset_type == "image"
                else None
            ),
            video_url=(
                self.assets.serialize(video).public_url
                if video is not None and video.asset_type == "video"
                else None
            ),
        )
