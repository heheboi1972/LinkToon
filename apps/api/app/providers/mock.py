import base64
import hashlib
from io import BytesIO
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from PIL import Image
from pydantic import JsonValue

from app.errors import GenerationError
from app.providers.base import (
    NormalizedProviderResult,
    ProviderArtifact,
    ProviderPollResult,
    ProviderRequest,
    ProviderResult,
    ProviderSubmitResult,
)


class MockProvider:
    """Deterministic development/test provider. It never calls an external AI service."""

    name = "mock"

    def submit(self, request: ProviderRequest) -> ProviderSubmitResult:
        task_id = self._task_id(request)
        retryable_failures = self._integer(request.input_data.get("mock_retryable_failures"), 0)
        if request.attempt < retryable_failures:
            return ProviderSubmitResult(
                status="failed",
                provider_task_id=task_id,
                error_code="mock_temporary_error",
                error_message="Mock provider simulated a temporary failure.",
                retryable=True,
            )
        if self._boolean(request.input_data.get("mock_fail")):
            return ProviderSubmitResult(
                status="failed",
                provider_task_id=task_id,
                error_code="mock_invalid_request",
                error_message="Mock provider simulated a non-retryable failure.",
            )
        if request.input_data.get("mock_mode") == "async":
            polls = max(0, self._integer(request.input_data.get("mock_pending_polls"), 1))
            return ProviderSubmitResult(
                status="pending",
                provider_task_id=task_id,
                state={"polls_remaining": polls},
            )
        return ProviderSubmitResult(
            status="completed",
            provider_task_id=task_id,
            state={"result": self._result(request)},
        )

    def poll(
        self,
        provider_task_id: str,
        request: ProviderRequest,
        state: dict[str, JsonValue],
    ) -> ProviderPollResult:
        if self._boolean(request.input_data.get("mock_poll_fail")):
            return ProviderPollResult(
                status="failed",
                provider_task_id=provider_task_id,
                error_code="mock_poll_error",
                error_message="Mock provider simulated a polling failure.",
                retryable=True,
                state=state,
            )
        remaining = max(0, self._integer(state.get("polls_remaining"), 0))
        if remaining > 0:
            return ProviderPollResult(
                status="pending",
                provider_task_id=provider_task_id,
                state={"polls_remaining": remaining - 1},
            )
        return ProviderPollResult(
            status="completed",
            provider_task_id=provider_task_id,
            state={"result": self._result(request)},
        )

    def cancel(self, provider_task_id: str, provider_model: str | None = None) -> None:
        # The mock task has no remote process. The method exists to exercise cancellation routing.
        if not provider_task_id:
            raise GenerationError("Mock provider task id is required for cancellation")

    def normalize_result(
        self, result: ProviderResult, request: ProviderRequest
    ) -> NormalizedProviderResult:
        payload = result.state.get("result")
        if not isinstance(payload, dict):
            raise GenerationError("Mock provider returned an invalid result")
        output = payload.get("output")
        artifacts = payload.get("artifacts", [])
        return NormalizedProviderResult.model_validate(
            {
                "kind": request.kind,
                "output": output,
                "artifacts": artifacts,
                "metadata": {"provider": "mock", "model": "mock-deterministic-v1"},
                "mock": True,
            }
        )

    def _result(self, request: ProviderRequest) -> dict[str, JsonValue]:
        if request.kind == "story":
            return self._story(request)
        if request.kind == "image":
            return self._image(request)
        if request.kind == "character":
            return self._character(request)
        return self._video(request)

    def _story(self, request: ProviderRequest) -> dict[str, JsonValue]:
        idea = self._text(request.input_data.get("idea"), "A LinkToon pipeline test")
        genre = self._text(request.input_data.get("genre"), "fantasy")
        theme = self._text(request.input_data.get("theme"), "courage")
        scene_count = min(20, max(1, self._integer(request.input_data.get("scene_count"), 3)))
        character_ids = self._character_ids(request.input_data.get("characters", []))
        scenes: list[JsonValue] = [
            {
                "order": index,
                "title": f"Mock Scene {index}",
                "narration": f"Development-only mock narration for scene {index}.",
                "dialogue": [],
                "visual_prompt": f"Mock {genre} scene about {theme}; scene {index}.",
                "character_ids": character_ids,
            }
            for index in range(1, scene_count + 1)
        ]
        return {
            "output": {
                "title": f"Mock Story: {idea[:60]}",
                "synopsis": "Mock provider generated this story for pipeline testing only.",
                "scenes": scenes,
            },
            "artifacts": [],
        }

    def _image(self, request: ProviderRequest) -> dict[str, JsonValue]:
        digest = hashlib.sha256(str(request.job_id).encode()).digest()
        content = BytesIO()
        Image.new("RGB", (16, 16), tuple(digest[:3])).save(content, "PNG")
        prompt = self._text(request.input_data.get("prompt"), "Mock image pipeline test")
        artifact = ProviderArtifact(
            asset_type="image",
            mime_type="image/png",
            filename="mock-generated.png",
            content_base64=base64.b64encode(content.getvalue()).decode("ascii"),
            width=16,
            height=16,
            prompt=prompt,
            metadata={
                "mock": True,
                "development_only": True,
                "reference_asset_ids": [str(item.asset_id) for item in request.reference_images],
                "reference_character_ids": [
                    str(item.character_id) for item in request.reference_images
                ],
                "reference_count": len(request.reference_images),
            },
        )
        return {
            "output": {
                "message": "Development-only mock image generated for pipeline testing.",
                "mock": True,
            },
            "artifacts": [artifact.model_dump(mode="json")],
        }

    def _character(self, request: ProviderRequest) -> dict[str, JsonValue]:
        name = self._text(request.input_data.get("name"), "Mock Character")
        digest = hashlib.sha256(f"{request.job_id}:character-reference".encode()).digest()
        content = BytesIO()
        Image.new("RGB", (16, 16), tuple(digest[:3])).save(content, "PNG")
        artifact = ProviderArtifact(
            asset_type="image",
            mime_type="image/png",
            filename="mock-character-reference.png",
            content_base64=base64.b64encode(content.getvalue()).decode("ascii"),
            width=16,
            height=16,
            prompt=self._text(request.input_data.get("prompt"), "Mock character reference"),
            metadata={
                "mock": True,
                "development_only": True,
                "character_reference": True,
                "character_id": self._text(request.input_data.get("character_id"), ""),
                "character_revision": self._integer(
                    request.input_data.get("character_revision"), 1
                ),
            },
        )
        return {
            "output": {
                "name": name,
                "description": "Development-only mock character for pipeline testing.",
                "appearance": "Stable mock appearance description",
                "personality": "Curious and dependable",
                "clothing": "Blue mock testing jacket",
                "mock": True,
            },
            "artifacts": [artifact.model_dump(mode="json")],
        }

    def _video(self, request: ProviderRequest) -> dict[str, JsonValue]:
        video_bytes = (Path(__file__).parent / "fixtures" / "mock-motion.mp4").read_bytes()
        prompt = self._text(request.input_data.get("prompt"), "Mock Scene motion preview")
        artifact = ProviderArtifact(
            asset_type="video",
            mime_type="video/mp4",
            filename="mock-scene-motion.mp4",
            content_base64=base64.b64encode(video_bytes).decode("ascii"),
            duration_ms=1500,
            prompt=prompt,
            metadata={"mock": True, "development_only": True},
        )
        return {
            "output": {
                "message": "A playable development-only Motion preview was generated.",
                "mock": True,
            },
            "artifacts": [artifact.model_dump(mode="json")],
        }

    @staticmethod
    def _task_id(request: ProviderRequest) -> str:
        return str(uuid5(NAMESPACE_URL, f"linktoon:mock:{request.idempotency_key}"))

    @staticmethod
    def _boolean(value: JsonValue | None) -> bool:
        return value is True

    @staticmethod
    def _integer(value: JsonValue | None, default: int) -> int:
        return value if isinstance(value, int) and not isinstance(value, bool) else default

    @staticmethod
    def _text(value: JsonValue | None, default: str) -> str:
        return value.strip() if isinstance(value, str) and value.strip() else default

    @staticmethod
    def _character_ids(value: JsonValue | None) -> list[JsonValue]:
        if not isinstance(value, list):
            return []
        character_ids: list[JsonValue] = []
        for item in value:
            candidate = item.get("character_id") if isinstance(item, dict) else item
            if not isinstance(candidate, str):
                continue
            try:
                character_ids.append(str(UUID(candidate)))
            except ValueError:
                continue
        return character_ids
