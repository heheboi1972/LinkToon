from uuid import UUID, uuid4

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.auth import sign_token, verify_token
from app.config import Settings
from app.errors import ApplicationError
from app.image_validation import validate_image_bytes
from app.models import (
    Asset,
    Character,
    CharacterReference,
    MotionLayer,
    Panel,
    Project,
    PublicationScene,
    Scene,
)
from app.repository import Repository
from app.schemas import AssetOut, UploadRequest, UploadTicket
from app.storage import storage_for


class AssetService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def ticket(self, owner_id: UUID, data: UploadRequest) -> UploadTicket:
        Repository(self.db, owner_id).project(data.project_id)
        if data.file_size > self.settings.max_upload_bytes:
            raise ApplicationError("Images must be 10 MB or smaller", "file_too_large", 413)
        asset_id = uuid4()
        asset = Asset(
            id=asset_id,
            owner_id=owner_id,
            project_id=data.project_id,
            asset_type=data.asset_type,
            mime_type=data.mime_type,
            storage_provider=self.settings.storage_provider,
            storage_bucket=(
                self.settings.supabase_storage_bucket
                if self.settings.storage_provider == "supabase"
                else "local"
            ),
            storage_key=f"{owner_id}/{data.project_id}/{asset_id}",
            source="upload",
            file_size=data.file_size,
            metadata_json={"filename": data.filename},
        )
        self.db.add(asset)
        self.db.commit()
        token = sign_token(self.settings, asset_id, "upload", minutes=15)
        return UploadTicket(
            asset_id=asset_id,
            upload_url=f"{self.settings.api_public_url}/api/v1/assets/{asset_id}"
            f"/upload?token={token}",
        )

    def receive(self, asset_id: UUID, token: str, content: bytes, mime_type: str) -> None:
        if verify_token(self.settings, token, "upload") != asset_id:
            raise ApplicationError("Invalid upload ticket", "unauthorized", 401)
        asset = self.db.scalar(select(Asset).where(Asset.id == asset_id).with_for_update())
        if not asset:
            raise ApplicationError("Asset not found", "not_found", 404)
        if asset.upload_status != "pending":
            raise ApplicationError("Original assets cannot be overwritten", "immutable_asset", 409)
        if len(content) != asset.file_size or len(content) > self.settings.max_upload_bytes:
            raise ApplicationError(
                "Upload size does not match the ticket", "invalid_file_size", 413
            )
        if mime_type.split(";")[0] != asset.mime_type:
            raise ApplicationError("Content type does not match", "invalid_file_type", 415)
        asset.width, asset.height = validate_image_bytes(
            content, asset.mime_type, max_bytes=self.settings.max_upload_bytes
        )
        storage_for(self.settings).put(asset.storage_key, content, asset.mime_type)
        asset.upload_status = "uploaded"
        self.db.commit()

    def complete(self, owner_id: UUID, asset_id: UUID) -> AssetOut:
        asset = Repository(self.db, owner_id).asset(asset_id, lock=True)
        if asset.upload_status == "pending":
            raise ApplicationError("Upload the file before completing it", "upload_incomplete", 409)
        asset.upload_status = "ready"
        self.db.commit()
        return self.serialize(asset)

    def serialize(self, asset: Asset) -> AssetOut:
        data = {
            column.key: getattr(asset, column.key)
            for column in Asset.__mapper__.column_attrs
            if column.key != "metadata_json"
        }
        data["metadata"] = asset.metadata_json
        if asset.upload_status == "ready":
            token = sign_token(self.settings, asset.id, "media", minutes=15)
            data["public_url"] = (
                f"{self.settings.api_public_url}/api/v1/assets/{asset.id}/content?token={token}"
            )
        return AssetOut.model_validate(data)

    def content(self, asset_id: UUID, token: str) -> tuple[bytes, str]:
        if verify_token(self.settings, token, "media") != asset_id:
            raise ApplicationError("Invalid media token", "unauthorized", 401)
        asset = self.db.get(Asset, asset_id)
        if not asset or asset.upload_status != "ready":
            raise ApplicationError("Asset not found", "not_found", 404)
        return storage_for(self.settings).read(asset.storage_key), asset.mime_type

    def delete(self, owner_id: UUID, asset_id: UUID) -> None:
        asset = Repository(self.db, owner_id).asset(asset_id, lock=True)
        references = [
            Panel.image_asset_id,
            Scene.image_asset_id,
            Scene.video_asset_id,
            Project.thumbnail_asset_id,
            Character.primary_asset_id,
            Character.reference_asset_id,
            CharacterReference.asset_id,
            MotionLayer.mask_asset_id,
            PublicationScene.image_asset_id,
            PublicationScene.video_asset_id,
        ]
        if any(self.db.scalar(select(exists().where(column == asset_id))) for column in references):
            raise ApplicationError(
                "Remove this asset from its panel or cover first", "asset_in_use", 409
            )
        if asset.upload_status != "pending":
            storage_for(self.settings).delete(asset.storage_key)
        self.db.delete(asset)
        self.db.commit()

    def media_content(
        self, asset_id: UUID, token: str, range_header: str | None
    ) -> tuple[bytes, str, int, dict[str, str]]:
        if verify_token(self.settings, token, "media") != asset_id:
            raise ApplicationError("Invalid media token", "unauthorized", 401)
        return self.read_media(asset_id, range_header)

    def read_media(
        self, asset_id: UUID, range_header: str | None
    ) -> tuple[bytes, str, int, dict[str, str]]:
        asset = self.db.get(Asset, asset_id)
        if not asset or asset.upload_status != "ready":
            raise ApplicationError("Asset not found", "not_found", 404)
        common = {"Accept-Ranges": "bytes"} if asset.asset_type == "video" else {}
        if asset.asset_type != "video" or not range_header:
            return (
                storage_for(self.settings).read(asset.storage_key),
                asset.mime_type,
                200,
                {**common, "Content-Length": str(asset.file_size)},
            )
        parsed = self._parse_byte_range(range_header, asset.file_size)
        if parsed is None:
            return (
                b"",
                asset.mime_type,
                416,
                {**common, "Content-Range": f"bytes */{asset.file_size}", "Content-Length": "0"},
            )
        start, end = parsed
        storage = storage_for(self.settings)
        reader = getattr(storage, "read_range", None)
        content = (
            reader(asset.storage_key, start, end)
            if callable(reader)
            else storage.read(asset.storage_key)[start : end + 1]
        )
        return (
            content,
            asset.mime_type,
            206,
            {
                **common,
                "Content-Range": f"bytes {start}-{end}/{asset.file_size}",
                "Content-Length": str(len(content)),
            },
        )

    @staticmethod
    def _parse_byte_range(value: str, size: int) -> tuple[int, int] | None:
        if not value.startswith("bytes=") or "," in value or size <= 0:
            return None
        try:
            start_text, end_text = value[6:].split("-", 1)
            if not start_text:
                suffix = int(end_text)
                if suffix <= 0:
                    return None
                return max(0, size - suffix), size - 1
            start = int(start_text)
            end = min(int(end_text), size - 1) if end_text else size - 1
        except ValueError:
            return None
        if start < 0 or end < start or start >= size:
            return None
        return start, end
