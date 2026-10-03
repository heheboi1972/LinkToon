import base64
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

from PIL import Image

from app.config import Settings
from app.providers.base import ProviderReferenceImage, ProviderRequest
from app.providers.openai import OpenAIProvider


def encoded_png() -> str:
    output = BytesIO()
    Image.new("RGB", (16, 16), "#6d28d9").save(output, "PNG")
    return base64.b64encode(output.getvalue()).decode("ascii")


class FakeImages:
    def __init__(self) -> None:
        self.generate_calls: list[dict[str, object]] = []
        self.edit_calls: list[dict[str, object]] = []

    def generate(self, **kwargs: object) -> object:
        self.generate_calls.append(kwargs)
        return SimpleNamespace(
            _request_id="generate", data=[SimpleNamespace(b64_json=encoded_png())]
        )

    def edit(self, **kwargs: object) -> object:
        self.edit_calls.append(kwargs)
        return SimpleNamespace(_request_id="edit", data=[SimpleNamespace(b64_json=encoded_png())])


def test_reference_scene_uses_edit_with_ordered_reference_files() -> None:
    settings = Settings(_env_file=None, mock_ai=False, openai_api_key="test-secret")
    images = FakeImages()
    provider = OpenAIProvider(
        settings, client=SimpleNamespace(images=images, responses=SimpleNamespace())
    )
    request = ProviderRequest(
        job_id=uuid4(),
        kind="image",
        action="scene",
        input_data={
            "scene_id": str(uuid4()),
            "episode_id": str(uuid4()),
            "prompt": "A scene with two characters",
            "character_ids": [str(uuid4()), str(uuid4())],
            "reference_asset_ids": [str(uuid4()), str(uuid4())],
            "reference_assets": [],
        },
        attempt=0,
        idempotency_key="edit-reference",
        reference_images=[
            ProviderReferenceImage(
                character_id=uuid4(),
                asset_id=uuid4(),
                mime_type="image/png",
                content_base64=encoded_png(),
            ),
            ProviderReferenceImage(
                character_id=uuid4(),
                asset_id=uuid4(),
                mime_type="image/png",
                content_base64=encoded_png(),
            ),
        ],
    )
    result = provider.submit(request)
    assert result.status == "completed"
    assert len(images.edit_calls) == 1
    assert len(images.edit_calls[0]["image"]) == 2
    assert images.edit_calls[0]["model"] == settings.openai_image_reference_model
    assert images.generate_calls == []


def test_character_reference_without_inputs_uses_reference_model_generate() -> None:
    settings = Settings(_env_file=None, mock_ai=False, openai_api_key="test-secret")
    images = FakeImages()
    provider = OpenAIProvider(
        settings, client=SimpleNamespace(images=images, responses=SimpleNamespace())
    )
    request = ProviderRequest(
        job_id=uuid4(),
        kind="character",
        action="reference",
        input_data={
            "character_id": str(uuid4()),
            "project_id": str(uuid4()),
            "name": "Mina",
            "prompt": "canonical reference",
            "character_revision": 1,
            "reference_type": "full_body",
            "prompt_version": "character-reference-v1",
        },
        attempt=0,
        idempotency_key="character-reference",
    )
    result = provider.submit(request)
    assert result.status == "completed"
    assert images.generate_calls[0]["model"] == settings.openai_image_reference_model
