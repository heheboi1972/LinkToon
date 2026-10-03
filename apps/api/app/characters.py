"""Owner-scoped Character Bible and reference Asset lifecycle."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assets import AssetService
from app.config import Settings
from app.errors import ApplicationError
from app.models import Asset, Character, CharacterReference, Episode, Project, Scene
from app.repository import Repository
from app.schemas import CharacterCreate, CharacterOut, CharacterPatch

_BIBLE_FIELDS = (
    "age_range",
    "gender_presentation",
    "face_description",
    "hair_description",
    "eye_description",
    "body_description",
    "accessories_description",
    "visual_style",
)


class CharacterService:
    def __init__(self, db: Session, owner_id: UUID, settings: Settings) -> None:
        self.db = db
        self.owner_id = owner_id
        self.settings = settings

    def serialize(self, character: Character) -> CharacterOut:
        reference_media_url: str | None = None
        if character.reference_asset_id:
            asset = self.db.get(Asset, character.reference_asset_id)
            if (
                asset
                and asset.upload_status == "ready"
                and asset.owner_id == self.owner_id
                and asset.project_id == character.project_id
            ):
                reference_media_url = (
                    AssetService(self.db, self.settings).serialize(asset).public_url
                )
        return CharacterOut.model_validate(
            {
                "id": character.id,
                "project_id": character.project_id,
                "name": character.name,
                "description": character.description,
                "appearance": character.appearance,
                "personality": character.personality,
                "clothing": character.clothing,
                "prompt_token": character.prompt_token,
                "character_bible": character.character_bible or {},
                "appearance_lock": character.appearance_lock_json or {},
                "style_lock": character.style_lock_json or {},
                "primary_asset_id": character.primary_asset_id,
                "reference_asset_id": character.reference_asset_id,
                "reference_media_url": reference_media_url,
                "reference_stale": character.reference_stale,
                "character_revision": character.character_revision,
                "reference_generated_from_revision": character.reference_generated_from_revision,
                "created_at": character.created_at,
                "updated_at": character.updated_at,
            }
        )

    @staticmethod
    def _bible(
        data: CharacterCreate | CharacterPatch, existing: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        result = dict(existing or {})
        for field in _BIBLE_FIELDS:
            if field in data.model_fields_set:
                value = getattr(data, field)
                if value is not None:
                    result[field] = value
        return result

    def create(self, project_id: UUID, data: CharacterCreate) -> CharacterOut:
        Repository(self.db, self.owner_id).project(project_id)
        character = Character(
            project_id=project_id,
            name=data.name,
            description=data.description,
            appearance=data.appearance,
            personality=data.personality,
            clothing=data.clothing,
            prompt_token=data.prompt_token,
            character_bible={"schema_version": 1, **self._bible(data)},
            appearance_lock_json=dict(data.appearance_lock),
            style_lock_json=dict(data.style_lock),
            character_revision=1,
            reference_stale=False,
        )
        self.db.add(character)
        self.db.commit()
        self.db.refresh(character)
        return self.serialize(character)

    def get(self, character_id: UUID) -> Character:
        character = self._character(character_id)
        return character

    def update(self, character_id: UUID, data: CharacterPatch) -> CharacterOut:
        character = self._character(character_id, lock=True)
        changed = False
        for field in (
            "name",
            "description",
            "appearance",
            "personality",
            "clothing",
            "prompt_token",
        ):
            if field in data.model_fields_set:
                value = getattr(data, field)
                if value != getattr(character, field):
                    setattr(character, field, value)
                    changed = True
        bible = self._bible(data, character.character_bible)
        if bible != (character.character_bible or {}):
            character.character_bible = bible
            changed = True
        if (
            "appearance_lock" in data.model_fields_set
            and data.appearance_lock != character.appearance_lock_json
        ):
            character.appearance_lock_json = dict(data.appearance_lock or {})
            changed = True
        if "style_lock" in data.model_fields_set and data.style_lock != character.style_lock_json:
            character.style_lock_json = dict(data.style_lock or {})
            changed = True
        if changed:
            character.character_revision += 1
            if character.reference_asset_id:
                character.reference_stale = True
        self.db.commit()
        self.db.refresh(character)
        return self.serialize(character)

    def delete(self, character_id: UUID) -> None:
        character = self._character(character_id, lock=True)
        scenes = self.db.scalars(
            select(Scene).join(Episode).where(Episode.project_id == character.project_id)
        )
        target = str(character.id)
        if any(
            isinstance(scene.script, dict) and target in scene.script.get("character_ids", [])
            for scene in scenes
        ):
            raise ApplicationError(
                "This character is used by a saved Story Scene and cannot be deleted.",
                "character_in_use",
                409,
            )
        self.db.delete(character)
        self.db.commit()

    def select_reference(self, character_id: UUID, asset_id: UUID) -> CharacterOut:
        character = self._character(character_id, lock=True)
        asset = Repository(self.db, self.owner_id).image(asset_id, character.project_id)
        if asset.asset_type != "image":
            raise ApplicationError(
                "Reference Asset must be a ready image", "invalid_reference_asset", 422
            )
        character.reference_asset_id = asset.id
        character.reference_generated_from_revision = character.character_revision
        character.reference_stale = False
        if not self.db.scalar(
            select(CharacterReference.id).where(
                CharacterReference.character_id == character.id,
                CharacterReference.asset_id == asset.id,
                CharacterReference.reference_type == "full_body",
            )
        ):
            self.db.add(
                CharacterReference(
                    character_id=character.id,
                    asset_id=asset.id,
                    reference_type="full_body",
                )
            )
        self.db.commit()
        self.db.refresh(character)
        return self.serialize(character)

    def clear_reference(self, character_id: UUID) -> CharacterOut:
        character = self._character(character_id, lock=True)
        character.reference_asset_id = None
        character.reference_generated_from_revision = None
        character.reference_stale = False
        self.db.commit()
        self.db.refresh(character)
        return self.serialize(character)

    def _character(self, character_id: UUID, *, lock: bool = False) -> Character:
        # Keep the owner check explicit through the project join; this prevents
        # leaking ids from another user's project.
        query = (
            select(Character)
            .join(Project)
            .where(
                Character.id == character_id,
                Project.owner_id == self.owner_id,
            )
        )
        if lock:
            query = query.with_for_update(of=Character)
        character = self.db.scalar(query)
        if character is None:
            raise ApplicationError("Character not found", "not_found", 404)
        return character
