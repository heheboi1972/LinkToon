import base64
import binascii
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from hmac import compare_digest
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import JsonValue, TypeAdapter, ValidationError
from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from app.config import Settings
from app.errors import ApplicationError, GenerationError, ProviderError, StorageError
from app.image_validation import validate_image_bytes, validate_video_bytes
from app.models import (
    Asset,
    Character,
    CharacterReference,
    Episode,
    GenerationJob,
    Project,
    Scene,
    utcnow,
)
from app.providers import (
    GenerationKind,
    GenerationProvider,
    NormalizedProviderResult,
    ProviderInputImage,
    ProviderPollResult,
    ProviderReferenceImage,
    ProviderRegistry,
    ProviderRequest,
    ProviderSubmitResult,
)
from app.storage import Storage, storage_for
from app.story_generation import StoryResult, validate_story_result

logger = logging.getLogger(__name__)
JsonObject = dict[str, JsonValue]
json_object = TypeAdapter(JsonObject)
ProcessingPhase = Literal["submit", "poll", "saving"]


@dataclass(frozen=True)
class ClaimedJob:
    id: UUID
    status: str
    recovered: bool


@dataclass(frozen=True)
class JobSnapshot:
    id: UUID
    user_id: UUID
    project_id: UUID
    job_type: str
    status: str
    provider: str | None
    provider_model: str | None
    provider_task_id: str | None
    input_data: JsonObject
    provider_output: JsonObject
    retry_count: int
    idempotency_key: str | None


class JobQueue:
    """Atomically leases database-backed jobs without holding a provider-call transaction."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        settings: Settings,
    ) -> None:
        self.sessions = sessions
        self.settings = settings

    @staticmethod
    def eligible(now: datetime) -> ColumnElement[bool]:
        due = or_(GenerationJob.next_poll_at.is_(None), GenerationJob.next_poll_at <= now)
        lease_available = or_(
            GenerationJob.lease_expires_at.is_(None), GenerationJob.lease_expires_at <= now
        )
        processable = and_(
            GenerationJob.status.in_(("queued", "running", "provider_pending", "saving")),
            due,
        )
        cancelable = and_(
            GenerationJob.status == "canceled",
            GenerationJob.provider_task_id.is_not(None),
            GenerationJob.next_poll_at.is_not(None),
            GenerationJob.next_poll_at <= now,
        )
        return and_(lease_available, or_(processable, cancelable))

    def claim(self, worker_id: str, *, now: datetime | None = None) -> ClaimedJob | None:
        claimed_at = now or utcnow()
        priority = case(
            (GenerationJob.status == "saving", 0),
            (GenerationJob.status == "provider_pending", 1),
            (GenerationJob.status == "running", 2),
            (GenerationJob.status == "canceled", 3),
            else_=4,
        )
        with self.sessions() as db:
            candidates = list(
                db.scalars(
                    select(GenerationJob)
                    .where(self.eligible(claimed_at))
                    .order_by(priority, GenerationJob.created_at)
                    .limit(8)
                    .with_for_update(skip_locked=True)
                )
            )
            for job in candidates:
                previous_status = job.status
                values: dict[str, object] = {
                    "lease_owner": worker_id,
                    "lease_expires_at": claimed_at
                    + timedelta(seconds=self.settings.worker_lease_seconds),
                    "updated_at": claimed_at,
                }
                if previous_status == "queued":
                    values.update(
                        status="running",
                        started_at=job.started_at or claimed_at,
                        next_poll_at=None,
                    )
                elif previous_status == "running" and job.provider_task_id:
                    values.update(status="provider_pending", next_poll_at=None)
                claimed_id = db.scalar(
                    update(GenerationJob)
                    .where(GenerationJob.id == job.id, self.eligible(claimed_at))
                    .values(**values)
                    .returning(GenerationJob.id)
                    .execution_options(synchronize_session=False)
                )
                if claimed_id is None:
                    db.rollback()
                    continue
                db.commit()
                claimed_status = str(values.get("status", previous_status))
                recovered = previous_status in {"running", "saving"}
                logger.info(
                    "worker=%s claimed job=%s type=%s status=%s recovered=%s",
                    worker_id,
                    job.id,
                    job.job_type,
                    claimed_status,
                    recovered,
                )
                return ClaimedJob(job.id, claimed_status, recovered)
        return None


class JobProcessor:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        settings: Settings,
        registry: ProviderRegistry,
        storage: Storage | None = None,
    ) -> None:
        self.sessions = sessions
        self.settings = settings
        self.registry = registry
        self.storage = storage or storage_for(settings)

    def process(self, job_id: UUID, worker_id: str) -> None:
        snapshot = self._snapshot(job_id, worker_id)
        if snapshot is None:
            return
        logger.info(
            "worker=%s processing job=%s type=%s state=%s provider=%s",
            worker_id,
            snapshot.id,
            snapshot.job_type,
            snapshot.status,
            snapshot.provider,
        )
        try:
            if snapshot.status == "canceled":
                self._cancel(snapshot, worker_id)
            elif snapshot.status == "saving":
                self._save(snapshot, worker_id)
            elif snapshot.status == "provider_pending" or snapshot.provider_task_id:
                self._poll(snapshot, worker_id)
            elif snapshot.status == "running":
                self._submit(snapshot, worker_id)
            else:
                self._release(snapshot.id, worker_id)
        except (ValidationError, GenerationError) as exc:
            phase = self._current_phase(snapshot)
            self._failure(
                snapshot.id,
                worker_id,
                "invalid_provider_result",
                str(exc),
                False,
                phase,
            )
        except (ProviderError, StorageError) as exc:
            phase = self._current_phase(snapshot)
            self._failure(snapshot.id, worker_id, exc.code, exc.message, True, phase)
        except ApplicationError as exc:
            phase = self._current_phase(snapshot)
            self._failure(snapshot.id, worker_id, exc.code, exc.message, False, phase)
        except Exception as exc:
            logger.error(
                "worker=%s job=%s unexpected_failure=%s",
                worker_id,
                snapshot.id,
                type(exc).__name__,
            )
            phase = self._current_phase(snapshot)
            self._failure(
                snapshot.id,
                worker_id,
                "worker_error",
                "The background worker could not process this job.",
                True,
                phase,
            )

    def _submit(self, snapshot: JobSnapshot, worker_id: str) -> None:
        provider = self.registry.resolve(self._provider_name(snapshot))
        request = self._request(snapshot)
        result = provider.submit(request)
        next_step = self._apply_provider_result(snapshot.id, worker_id, provider, request, result)
        if next_step == "saving":
            saving = self._snapshot(snapshot.id, worker_id)
            if saving:
                self._save(saving, worker_id)

    def _poll(self, snapshot: JobSnapshot, worker_id: str) -> None:
        if not snapshot.provider_task_id:
            self._failure(
                snapshot.id,
                worker_id,
                "provider_task_missing",
                "Provider task id is missing for a pending job.",
                False,
                "poll",
            )
            return
        provider = self.registry.resolve(self._provider_name(snapshot))
        request = self._request(snapshot)
        state_value = snapshot.provider_output.get("state", {})
        state = json_object.validate_python(state_value)
        result = provider.poll(snapshot.provider_task_id, request, state)
        next_step = self._apply_provider_result(snapshot.id, worker_id, provider, request, result)
        if next_step == "saving":
            saving = self._snapshot(snapshot.id, worker_id)
            if saving:
                self._save(saving, worker_id)

    def _apply_provider_result(
        self,
        job_id: UUID,
        worker_id: str,
        provider: GenerationProvider,
        request: ProviderRequest,
        result: ProviderSubmitResult | ProviderPollResult,
    ) -> Literal["saving", "pending", "failed", "canceled", "lost"]:
        if result.status == "canceled":
            with self.sessions() as db:
                job = db.scalar(
                    select(GenerationJob).where(GenerationJob.id == job_id).with_for_update()
                )
                if not job or job.lease_owner != worker_id:
                    return "lost"
                job.status = "canceled"
                job.provider_task_id = result.provider_task_id
                job.provider_output = {"state": result.state}
                job.completed_at = utcnow()
                job.next_poll_at = None
                job.error_code = result.error_code
                job.error_message = result.error_message
                self._clear_lease(job)
                db.commit()
            logger.info("worker=%s job=%s state=canceled provider=true", worker_id, job_id)
            return "canceled"
        if result.status == "failed":
            poll_failure = isinstance(result, ProviderPollResult)
            self._failure(
                job_id,
                worker_id,
                result.error_code or "provider_failed",
                result.error_message or "Generation provider failed.",
                result.retryable,
                "poll" if poll_failure else "submit",
                provider_task_id=result.provider_task_id if poll_failure else None,
                provider_state=result.state,
            )
            return "failed"
        normalized: NormalizedProviderResult | None = None
        if result.status == "completed":
            normalized = provider.normalize_result(result, request)
        canceled = False
        with self.sessions() as db:
            job = db.scalar(
                select(GenerationJob).where(GenerationJob.id == job_id).with_for_update()
            )
            if not job:
                return "lost"
            if job.status == "canceled":
                job.provider_task_id = result.provider_task_id
                job.provider_output = {"state": result.state}
                self._clear_lease(job)
                db.commit()
                canceled = True
            elif job.lease_owner != worker_id:
                return "lost"
            elif result.status == "pending":
                job.provider_task_id = result.provider_task_id
                job.provider_output = {"state": result.state}
                job.status = "provider_pending"
                job.progress = max(job.progress, 40)
                job.next_poll_at = utcnow() + timedelta(
                    seconds=(
                        result.poll_after_seconds or self.settings.worker_provider_poll_seconds
                    )
                )
                job.error_code = None
                job.error_message = None
                self._clear_lease(job)
                db.commit()
                logger.info("worker=%s job=%s state=provider_pending", worker_id, job_id)
                return "pending"
            elif normalized is not None:
                job.provider_task_id = result.provider_task_id
                job.provider_output = normalized.model_dump(mode="json")
                model = normalized.metadata.get("model")
                if isinstance(model, str) and model:
                    job.provider_model = model
                job.status = "saving"
                job.progress = max(job.progress, 80)
                job.next_poll_at = None
                job.error_code = None
                job.error_message = None
                db.commit()
                logger.info("worker=%s job=%s state=saving", worker_id, job_id)
                return "saving"
        if canceled:
            provider.cancel(result.provider_task_id, request.provider_model)
            logger.info("worker=%s job=%s provider_cancelled=true", worker_id, job_id)
            return "canceled"
        return "lost"

    def _save(self, snapshot: JobSnapshot, worker_id: str) -> None:
        story: StoryResult | None = None
        try:
            normalized = NormalizedProviderResult.model_validate(snapshot.provider_output)
            if normalized.kind == "story":
                scene_count, allowed_ids = self._story_context(snapshot.input_data)
                story = validate_story_result(
                    normalized.output,
                    scene_count=scene_count,
                    allowed_ids=allowed_ids,
                )
            provider = self.registry.resolve(self._provider_name(snapshot))
            stored = self._store_artifacts(snapshot, normalized, provider)
        except StorageError as exc:
            self._failure(snapshot.id, worker_id, exc.code, exc.message, True, "saving")
            return
        except GenerationError as exc:
            self._failure(
                snapshot.id,
                worker_id,
                "invalid_story_result",
                exc.message,
                False,
                "saving",
            )
            return
        except (ValueError, ValidationError, binascii.Error) as exc:
            self._failure(
                snapshot.id,
                worker_id,
                "invalid_artifact",
                f"Provider artifact could not be saved: {type(exc).__name__}",
                False,
                "saving",
            )
            return

        try:
            with self.sessions() as db:
                job = db.scalar(
                    select(GenerationJob).where(GenerationJob.id == snapshot.id).with_for_update()
                )
                if not job or job.lease_owner != worker_id:
                    return
                if job.status == "canceled":
                    self._clear_lease(job)
                    db.commit()
                    return
                asset_ids: list[JsonValue] = []
                for item in stored:
                    asset = db.get(Asset, item.asset_id)
                    if asset is None:
                        artifact = normalized.artifacts[item.position]
                        asset = Asset(
                            id=item.asset_id,
                            owner_id=job.user_id,
                            project_id=job.project_id,
                            asset_type=artifact.asset_type,
                            mime_type=artifact.mime_type,
                            storage_provider=self.settings.storage_provider,
                            storage_bucket=(
                                self.settings.supabase_storage_bucket
                                if self.settings.storage_provider == "supabase"
                                else "local"
                            ),
                            storage_key=item.storage_key,
                            source="generated",
                            provider=job.provider,
                            provider_task_id=job.provider_task_id,
                            generation_job_id=job.id,
                            prompt=artifact.prompt,
                            width=item.width or artifact.width,
                            height=item.height or artifact.height,
                            duration_ms=artifact.duration_ms,
                            file_size=len(item.content),
                            metadata_json={
                                **artifact.metadata,
                                "filename": artifact.filename,
                                "mock_provider": normalized.mock,
                            },
                            upload_status="ready",
                        )
                        db.add(asset)
                    elif (
                        asset.generation_job_id != job.id
                        or asset.storage_key != item.storage_key
                        or asset.owner_id != job.user_id
                    ):
                        raise GenerationError("Generated Asset save target is inconsistent")
                    asset_ids.append(str(item.asset_id))
                output: JsonObject = dict(normalized.output)
                if story is not None:
                    episode_id, scene_ids = self._save_story(db, job, story)
                    output["episode_id"] = str(episode_id)
                    output["scene_ids"] = [str(scene_id) for scene_id in scene_ids]
                if (
                    normalized.kind == "image"
                    and job.job_type == "image:scene"
                    and isinstance(job.input, dict)
                    and isinstance(job.input.get("scene_id"), str)
                ):
                    scene_id, asset_id = self._link_scene_image(db, job, stored)
                    output["scene_id"] = str(scene_id)
                    output["asset_id"] = str(asset_id)
                if normalized.kind == "character" and job.job_type == "character:reference":
                    character_id, asset_id = self._link_character_reference(db, job, stored)
                    output["character_id"] = str(character_id)
                    output["reference_asset_id"] = str(asset_id)
                if normalized.kind == "video" and job.job_type == "video:scene":
                    scene_id, asset_id = self._link_scene_video(db, job, stored)
                    output["scene_id"] = str(scene_id)
                    output["video_asset_id"] = str(asset_id)
                    # The provider URL is only needed while a saving Job recovers.
                    job.provider_output = {}
                output["asset_ids"] = asset_ids
                output["provider_metadata"] = normalized.metadata
                output["mock"] = normalized.mock
                if normalized.metadata.get("provider") == "fal":
                    # The temporary fal.ai output URL is needed only during saving recovery.
                    job.provider_output = {}
                job.output = output
                job.status = "succeeded"
                job.progress = 100
                job.completed_at = utcnow()
                job.next_poll_at = None
                job.error_code = None
                job.error_message = None
                self._clear_lease(job)
                db.commit()
        except GenerationError as exc:
            self._failure(
                snapshot.id,
                worker_id,
                "invalid_image_save_target",
                exc.message,
                False,
                "saving",
            )
            return
        except SQLAlchemyError:
            self._failure(
                snapshot.id,
                worker_id,
                "database_save_error",
                "The generated result could not be saved to the database.",
                True,
                "saving",
            )
            return
        logger.info("worker=%s job=%s state=succeeded", worker_id, snapshot.id)

    def _save_story(
        self,
        db: Session,
        job: GenerationJob,
        story: StoryResult,
    ) -> tuple[UUID, list[UUID]]:
        referenced_ids = {
            character_id for scene in story.scenes for character_id in scene.character_ids
        }
        referenced_ids.update(
            dialogue.character_id
            for scene in story.scenes
            for dialogue in scene.dialogue
            if dialogue.character_id is not None
        )
        if referenced_ids:
            persisted_ids = set(
                db.scalars(
                    select(Character.id).where(
                        Character.project_id == job.project_id,
                        Character.id.in_(referenced_ids),
                    )
                )
            )
            if persisted_ids != referenced_ids:
                raise GenerationError(
                    "Story contains a character reference that no longer exists in the project"
                )

        episode_id = uuid5(NAMESPACE_URL, f"linktoon:story:{job.id}")
        episode = db.get(Episode, episode_id)
        if episode is None:
            project = db.scalar(
                select(Project).where(Project.id == job.project_id).with_for_update()
            )
            if project is None:
                raise GenerationError("Story project no longer exists")
            number = (
                db.scalar(
                    select(func.max(Episode.number)).where(Episode.project_id == job.project_id)
                )
                or 0
            ) + 1
            episode = Episode(
                id=episode_id,
                project_id=job.project_id,
                number=number,
                title=story.title,
                description=story.synopsis,
                status="draft",
            )
            db.add(episode)
            project.updated_at = utcnow()
            db.flush()
        elif episode.project_id != job.project_id:
            raise GenerationError("Story save target does not belong to the job project")

        scene_ids: list[UUID] = []
        for scene in story.scenes:
            scene_id = uuid5(NAMESPACE_URL, f"linktoon:story:{job.id}:scene:{scene.order}")
            saved_scene = db.get(Scene, scene_id)
            if saved_scene is None:
                saved_scene = Scene(
                    id=scene_id,
                    episode_id=episode_id,
                    position=scene.order - 1,
                    title=scene.title,
                    script={
                        "narration": scene.narration,
                        "dialogue": [
                            dialogue.model_dump(mode="json") for dialogue in scene.dialogue
                        ],
                        "visual_prompt": scene.visual_prompt,
                        "character_ids": [str(value) for value in scene.character_ids],
                        "generation_job_id": str(job.id),
                    },
                )
                db.add(saved_scene)
            elif saved_scene.episode_id != episode_id:
                raise GenerationError("Story Scene save target is inconsistent")
            scene_ids.append(scene_id)
        return episode_id, scene_ids

    @staticmethod
    def _link_scene_image(
        db: Session,
        job: GenerationJob,
        stored: list["StoredArtifact"],
    ) -> tuple[UUID, UUID]:
        if job.job_type != "image:scene" or len(stored) != 1:
            raise GenerationError("Scene image jobs must produce exactly one image")
        scene_value = job.input.get("scene_id") if isinstance(job.input, dict) else None
        episode_value = job.input.get("episode_id") if isinstance(job.input, dict) else None
        try:
            scene_id = UUID(scene_value) if isinstance(scene_value, str) else None
            episode_id = UUID(episode_value) if isinstance(episode_value, str) else None
        except ValueError as exc:
            raise GenerationError("Scene image save target is invalid") from exc
        if scene_id is None or episode_id is None:
            raise GenerationError("Scene image save target is missing")
        scene = db.scalar(
            select(Scene)
            .join(Episode)
            .where(
                Scene.id == scene_id,
                Scene.episode_id == episode_id,
                Episode.project_id == job.project_id,
            )
            .with_for_update(of=Scene)
        )
        if scene is None:
            raise GenerationError("Scene image save target no longer exists")
        scene.image_asset_id = stored[0].asset_id
        scene.updated_at = utcnow()
        return scene.id, stored[0].asset_id

    @staticmethod
    def _link_character_reference(
        db: Session,
        job: GenerationJob,
        stored: list["StoredArtifact"],
    ) -> tuple[UUID, UUID]:
        if job.job_type != "character:reference" or len(stored) != 1:
            raise GenerationError("Character reference jobs must produce exactly one image")
        value = job.input.get("character_id") if isinstance(job.input, dict) else None
        revision = job.input.get("character_revision") if isinstance(job.input, dict) else None
        try:
            character_id = UUID(value) if isinstance(value, str) else None
        except ValueError as exc:
            raise GenerationError("Character reference save target is invalid") from exc
        if character_id is None or not isinstance(revision, int):
            raise GenerationError("Character reference save target is missing")
        character = db.scalar(
            select(Character)
            .join(Project)
            .where(
                Character.id == character_id,
                Project.id == job.project_id,
                Project.owner_id == job.user_id,
            )
            .with_for_update(of=Character)
        )
        if character is None:
            raise GenerationError("Character reference save target no longer exists")
        character.reference_asset_id = stored[0].asset_id
        character.reference_generated_from_revision = revision
        character.reference_stale = character.character_revision != revision
        if not db.scalar(
            select(CharacterReference.id).where(
                CharacterReference.character_id == character.id,
                CharacterReference.asset_id == stored[0].asset_id,
                CharacterReference.reference_type == "full_body",
            )
        ):
            db.add(
                CharacterReference(
                    character_id=character.id,
                    asset_id=stored[0].asset_id,
                    reference_type="full_body",
                )
            )
        character.updated_at = utcnow()
        return character.id, stored[0].asset_id

    def _store_artifacts(
        self,
        snapshot: JobSnapshot,
        normalized: NormalizedProviderResult,
        provider: GenerationProvider,
    ) -> list["StoredArtifact"]:
        stored: list[StoredArtifact] = []
        for position, artifact in enumerate(normalized.artifacts):
            asset_id = uuid5(NAMESPACE_URL, f"linktoon:asset:{snapshot.id}:{position}")
            extension = {
                "image/png": "png",
                "image/jpeg": "jpg",
                "image/webp": "webp",
                "video/mp4": "mp4",
            }.get(artifact.mime_type)
            suffix = f".{extension}" if extension else ""
            key = (
                f"users/{snapshot.user_id}/projects/{snapshot.project_id}/generated/"
                f"{asset_id}{suffix}"
            )
            if artifact.source_url:
                is_video_url = (
                    normalized.kind == "video"
                    and artifact.asset_type == "video"
                    and artifact.mime_type == "video/mp4"
                )
                is_fal_image_url = (
                    normalized.kind in {"image", "character"}
                    and normalized.metadata.get("provider") == "fal"
                    and artifact.asset_type in {"image", "reference"}
                    and artifact.mime_type in {"image/png", "image/jpeg", "image/webp"}
                )
                if artifact.content_base64 or not (is_video_url or is_fal_image_url):
                    raise ValueError("Provider output URL is not allowed for this artifact")
                try:
                    content = self.storage.read(key)
                except StorageError:
                    content = b""
                if not content:
                    downloader = getattr(provider, "download_artifact", None)
                    if not callable(downloader):
                        raise ApplicationError(
                            "Provider cannot download its video result", "invalid_video", 422
                        )
                    content, downloaded_mime = downloader(
                        artifact.source_url, self.settings.max_video_bytes
                    )
                    if downloaded_mime != artifact.mime_type:
                        raise ApplicationError(
                            "Provider artifact type does not match its result",
                            "invalid_artifact_content_type",
                            415,
                        )
            else:
                if not artifact.content_base64:
                    raise ValueError("Artifact has no persisted content")
                maximum = (
                    self.settings.max_video_bytes
                    if artifact.asset_type == "video"
                    else self.settings.max_upload_bytes
                )
                maximum_encoded = ((maximum + 2) // 3) * 4 + 4
                if len(artifact.content_base64) > maximum_encoded:
                    raise ValueError("Artifact content exceeds the configured size limit")
                content = base64.b64decode(artifact.content_base64, validate=True)
            if not content:
                raise ValueError("Artifact content is empty")
            width: int | None = None
            height: int | None = None
            if artifact.asset_type in {"image", "reference"}:
                try:
                    width, height = validate_image_bytes(
                        content,
                        artifact.mime_type,
                        max_bytes=self.settings.max_upload_bytes,
                    )
                except ApplicationError as exc:
                    raise ValueError(exc.code) from exc
            elif artifact.asset_type == "video":
                validate_video_bytes(
                    content, artifact.mime_type, max_bytes=self.settings.max_video_bytes
                )
            elif artifact.source_url:
                raise ApplicationError(
                    "Only MP4 video results can be downloaded", "invalid_video", 415
                )
            try:
                self.storage.put(key, content, artifact.mime_type)
            except StorageError as original:
                try:
                    existing = self.storage.read(key)
                except StorageError as read_error:
                    raise original from read_error
                if not compare_digest(existing, content):
                    raise original
            stored.append(StoredArtifact(position, asset_id, key, content, width, height))
        return stored

    @staticmethod
    def _link_scene_video(
        db: Session, job: GenerationJob, stored: list["StoredArtifact"]
    ) -> tuple[UUID, UUID]:
        if job.job_type != "video:scene" or len(stored) != 1:
            raise GenerationError("Scene motion jobs must produce exactly one video")
        scene_value = job.input.get("scene_id") if isinstance(job.input, dict) else None
        episode_value = job.input.get("episode_id") if isinstance(job.input, dict) else None
        try:
            scene_id = UUID(scene_value) if isinstance(scene_value, str) else None
            episode_id = UUID(episode_value) if isinstance(episode_value, str) else None
        except ValueError as exc:
            raise GenerationError("Scene video save target is invalid") from exc
        if scene_id is None or episode_id is None:
            raise GenerationError("Scene video save target is missing")
        scene = db.scalar(
            select(Scene)
            .join(Episode)
            .where(
                Scene.id == scene_id,
                Scene.episode_id == episode_id,
                Episode.project_id == job.project_id,
            )
            .with_for_update(of=Scene)
        )
        if scene is None:
            raise GenerationError("Scene video save target no longer exists")
        scene.video_asset_id = stored[0].asset_id
        scene.updated_at = utcnow()
        return scene.id, stored[0].asset_id

    def _cancel(self, snapshot: JobSnapshot, worker_id: str) -> None:
        if snapshot.provider_task_id and snapshot.provider:
            provider = self.registry.resolve(snapshot.provider)
            try:
                provider.cancel(snapshot.provider_task_id, snapshot.provider_model)
            except ApplicationError:
                logger.warning(
                    "worker=%s job=%s provider_cancel_failed=true", worker_id, snapshot.id
                )
        with self.sessions() as db:
            job = db.scalar(
                select(GenerationJob).where(GenerationJob.id == snapshot.id).with_for_update()
            )
            if job and job.lease_owner == worker_id:
                job.next_poll_at = None
                self._clear_lease(job)
                db.commit()
        logger.info("worker=%s job=%s state=canceled", worker_id, snapshot.id)

    def _failure(
        self,
        job_id: UUID,
        worker_id: str,
        code: str,
        message: str,
        retryable: bool,
        phase: ProcessingPhase,
        *,
        provider_task_id: str | None = None,
        provider_state: JsonObject | None = None,
    ) -> None:
        with self.sessions() as db:
            job = db.scalar(
                select(GenerationJob).where(GenerationJob.id == job_id).with_for_update()
            )
            if not job or job.lease_owner != worker_id or job.status == "canceled":
                return
            if provider_task_id:
                job.provider_task_id = provider_task_id
            if provider_state is not None:
                job.provider_output = {"state": provider_state}
            job.error_code = code[:100]
            job.error_message = message
            if retryable and job.retry_count < self.settings.worker_max_retries:
                job.retry_count += 1
                delay = self.settings.worker_retry_base_seconds * (2 ** (job.retry_count - 1))
                job.next_poll_at = utcnow() + timedelta(seconds=delay)
                job.status = {
                    "submit": "queued",
                    "poll": "provider_pending",
                    "saving": "saving",
                }[phase]
                logger.warning(
                    "worker=%s job=%s retry=%s phase=%s code=%s",
                    worker_id,
                    job_id,
                    job.retry_count,
                    phase,
                    code,
                )
            else:
                job.status = "failed"
                job.completed_at = utcnow()
                job.next_poll_at = None
                if phase == "saving" and (job.job_type == "video:scene" or job.provider == "fal"):
                    job.provider_output = {}
                logger.warning(
                    "worker=%s job=%s state=failed phase=%s code=%s",
                    worker_id,
                    job_id,
                    phase,
                    code,
                )
            self._clear_lease(job)
            db.commit()

    def _snapshot(self, job_id: UUID, worker_id: str) -> JobSnapshot | None:
        with self.sessions() as db:
            job = db.scalar(
                select(GenerationJob).where(
                    GenerationJob.id == job_id, GenerationJob.lease_owner == worker_id
                )
            )
            if not job:
                return None
            return JobSnapshot(
                id=job.id,
                user_id=job.user_id,
                project_id=job.project_id,
                job_type=job.job_type,
                status=job.status,
                provider=job.provider,
                provider_model=job.provider_model,
                provider_task_id=job.provider_task_id,
                input_data=json_object.validate_python(job.input),
                provider_output=json_object.validate_python(job.provider_output),
                retry_count=job.retry_count,
                idempotency_key=job.idempotency_key,
            )

    def _release(self, job_id: UUID, worker_id: str) -> None:
        with self.sessions() as db:
            job = db.scalar(
                select(GenerationJob).where(
                    GenerationJob.id == job_id, GenerationJob.lease_owner == worker_id
                )
            )
            if job:
                self._clear_lease(job)
                db.commit()

    @staticmethod
    def _clear_lease(job: GenerationJob) -> None:
        job.lease_owner = None
        job.lease_expires_at = None

    @staticmethod
    def _provider_name(snapshot: JobSnapshot) -> str:
        if not snapshot.provider:
            raise ApplicationError("Job has no generation provider", "provider_not_configured", 503)
        return snapshot.provider

    @staticmethod
    def _phase(snapshot: JobSnapshot) -> ProcessingPhase:
        if snapshot.status == "saving":
            return "saving"
        if snapshot.status == "provider_pending" or snapshot.provider_task_id:
            return "poll"
        return "submit"

    def _current_phase(self, snapshot: JobSnapshot) -> ProcessingPhase:
        with self.sessions() as db:
            status = db.scalar(select(GenerationJob.status).where(GenerationJob.id == snapshot.id))
        if status == "saving":
            return "saving"
        if status == "provider_pending":
            return "poll"
        return self._phase(snapshot)

    @staticmethod
    def _story_context(input_data: JsonObject) -> tuple[int, set[UUID]]:
        scene_count = input_data.get("scene_count", 3)
        if (
            not isinstance(scene_count, int)
            or isinstance(scene_count, bool)
            or not 1 <= scene_count <= 20
        ):
            raise GenerationError("Story input has an invalid scene count")
        allowed_ids: set[UUID] = set()
        characters = input_data.get("characters", [])
        if not isinstance(characters, list):
            raise GenerationError("Story character context must be a list")
        for character in characters:
            if isinstance(character, dict):
                structured = True
                candidate = character.get("character_id")
            else:
                structured = False
                candidate = character
            if not isinstance(candidate, str):
                if structured:
                    raise GenerationError("Story character context has an invalid identifier")
                continue
            try:
                allowed_ids.add(UUID(candidate))
            except ValueError as exc:
                if structured:
                    raise GenerationError(
                        "Story character context has an invalid identifier"
                    ) from exc
        return scene_count, allowed_ids

    def _request(self, snapshot: JobSnapshot) -> ProviderRequest:
        category, separator, action = snapshot.job_type.partition(":")
        if not separator or not action:
            raise GenerationError("Job type must contain a generation category and action")
        if category == "motion":
            category = "video"
        if category == "story":
            kind: GenerationKind = "story"
        elif category == "image":
            kind = "image"
        elif category == "character":
            kind = "character"
        elif category == "video":
            kind = "video"
        else:
            raise GenerationError("Job has an unsupported generation category")
        references: list[ProviderReferenceImage] = []
        source_image: ProviderInputImage | None = None
        if kind == "video" and action == "scene":
            value = snapshot.input_data.get("image_asset_id")
            try:
                image_id = UUID(value) if isinstance(value, str) else None
            except ValueError as exc:
                raise GenerationError("Scene motion image reference is invalid") from exc
            if image_id is None:
                raise GenerationError("Scene motion image reference is missing")
            with self.sessions() as db:
                image = db.scalar(
                    select(Asset).where(
                        Asset.id == image_id,
                        Asset.owner_id == snapshot.user_id,
                        Asset.project_id == snapshot.project_id,
                        Asset.asset_type == "image",
                        Asset.upload_status == "ready",
                    )
                )
                if image is None or image.mime_type not in {
                    "image/png",
                    "image/jpeg",
                    "image/webp",
                }:
                    raise GenerationError("Scene motion image is unavailable")
                try:
                    content = self.storage.read(image.storage_key)
                    validate_image_bytes(content, image.mime_type, max_bytes=5 * 1024 * 1024)
                except (StorageError, ApplicationError) as exc:
                    raise GenerationError("Scene motion image could not be read") from exc
                source_image = ProviderInputImage(
                    asset_id=image.id,
                    mime_type=image.mime_type,
                    content_base64=base64.b64encode(content).decode("ascii"),
                )
        raw_references = snapshot.input_data.get("reference_assets", [])
        if raw_references:
            if not isinstance(raw_references, list) or len(raw_references) > 4:
                raise GenerationError("Character reference input is invalid")
            with self.sessions() as db:
                for item in raw_references:
                    if not isinstance(item, dict):
                        raise GenerationError("Character reference input is invalid")
                    asset_value = item.get("asset_id")
                    character_value = item.get("character_id")
                    if not isinstance(asset_value, str) or not isinstance(character_value, str):
                        raise GenerationError("Character reference input is invalid")
                    try:
                        asset_id = UUID(asset_value)
                        character_id = UUID(character_value)
                    except ValueError as exc:
                        raise GenerationError("Character reference input is invalid") from exc
                    asset = db.scalar(
                        select(Asset).where(
                            Asset.id == asset_id,
                            Asset.owner_id == snapshot.user_id,
                            Asset.project_id == snapshot.project_id,
                        )
                    )
                    if (
                        asset is None
                        or asset.upload_status != "ready"
                        or asset.asset_type != "image"
                    ):
                        raise GenerationError("Character reference Asset is unavailable")
                    if not asset.mime_type.startswith("image/"):
                        raise GenerationError("Character reference Asset must be an image")
                    try:
                        content = self.storage.read(asset.storage_key)
                        validate_image_bytes(
                            content, asset.mime_type, max_bytes=self.settings.max_upload_bytes
                        )
                    except (StorageError, ApplicationError) as exc:
                        raise GenerationError(
                            "Character reference Asset could not be read"
                        ) from exc
                    references.append(
                        ProviderReferenceImage(
                            character_id=character_id,
                            asset_id=asset.id,
                            mime_type=asset.mime_type,
                            content_base64=base64.b64encode(content).decode("ascii"),
                        )
                    )
        return ProviderRequest(
            job_id=snapshot.id,
            kind=kind,
            action=action,
            provider_model=snapshot.provider_model,
            input_data=snapshot.input_data,
            attempt=snapshot.retry_count,
            idempotency_key=snapshot.idempotency_key or str(snapshot.id),
            reference_images=references,
            source_image=source_image,
        )


@dataclass(frozen=True)
class StoredArtifact:
    position: int
    asset_id: UUID
    storage_key: str
    content: bytes
    width: int | None
    height: int | None


class DatabaseWorker:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        settings: Settings,
        registry: ProviderRegistry,
        worker_id: str,
    ) -> None:
        self.queue = JobQueue(sessions, settings)
        self.processor = JobProcessor(sessions, settings, registry)
        self.settings = settings
        self.worker_id = worker_id

    def run_once(self) -> bool:
        claimed = self.queue.claim(self.worker_id)
        if claimed is None:
            return False
        self.processor.process(claimed.id, self.worker_id)
        return True

    def run_batch(self) -> int:
        processed = 0
        for _ in range(self.settings.worker_batch_size):
            if not self.run_once():
                break
            processed += 1
        return processed
