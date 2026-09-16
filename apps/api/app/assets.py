import warnings
from io import BytesIO
from uuid import UUID, uuid4

from PIL import Image, UnidentifiedImageError
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.auth import sign_token, verify_token
from app.config import Settings
from app.errors import ApplicationError
from app.models import Asset, Character, CharacterReference, MotionLayer, Panel, Project
from app.repository import Repository
from app.schemas import AssetOut, UploadRequest, UploadTicket
from app.storage import storage_for

MIME_FORMAT = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}


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
            storage_key=f"{owner_id}/{data.project_id}/{asset_id}",
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
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(content)) as image:
                    if image.format != MIME_FORMAT.get(asset.mime_type):
                        raise ValueError("Image content does not match the declared type")
                    if getattr(image, "n_frames", 1) != 1:
                        raise ValueError("Only static images are supported in Phase 1")
                    if image.width * image.height > 25_000_000:
                        raise ValueError("Image exceeds 25 megapixels")
                    image.verify()
                with Image.open(BytesIO(content)) as image:
                    image.load()
                    asset.width, asset.height = image.size
        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as exc:
            raise ApplicationError(
                "File must be a valid static PNG, JPEG or WebP image", "invalid_image", 415
            ) from exc
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
            Project.thumbnail_asset_id,
            Character.primary_asset_id,
            CharacterReference.asset_id,
            MotionLayer.mask_asset_id,
        ]
        if any(self.db.scalar(select(exists().where(column == asset_id))) for column in references):
            raise ApplicationError(
                "Remove this asset from its panel or cover first", "asset_in_use", 409
            )
        if asset.upload_status != "pending":
            storage_for(self.settings).delete(asset.storage_key)
        self.db.delete(asset)
        self.db.commit()
