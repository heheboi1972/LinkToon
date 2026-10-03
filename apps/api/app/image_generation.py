"""Domain input and prompt construction for Scene image generation."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models import Character, Project, ProjectBible, Scene


class ReferenceAssetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character_id: UUID
    asset_id: UUID


class SceneImageProviderInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    scene_id: UUID
    episode_id: UUID
    prompt: str = Field(min_length=1, max_length=32_000)
    character_ids: list[UUID] = Field(default_factory=list, max_length=20)
    reference_asset_ids: list[UUID] = Field(default_factory=list, max_length=4)
    reference_assets: list["ReferenceAssetInput"] = Field(default_factory=list, max_length=4)
    prompt_version: str = "character-consistency-v1"


class CharacterReferenceProviderInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    character_id: UUID
    project_id: UUID
    name: str = Field(min_length=1, max_length=80)
    prompt: str = Field(min_length=1, max_length=32_000)
    character_revision: int = Field(ge=1)
    reference_type: str = "full_body"
    prompt_version: str = "character-reference-v1"


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _character_line(character: Character) -> str:
    details = [
        f"name: {character.name}",
        f"appearance: {character.appearance}" if character.appearance else "",
        f"clothing: {character.clothing}" if character.clothing else "",
    ]
    bible = character.character_bible if isinstance(character.character_bible, dict) else {}
    labels = {
        "age_range": "age",
        "gender_presentation": "gender presentation",
        "face_description": "face",
        "hair_description": "hair",
        "eye_description": "eyes",
        "body_description": "body",
        "accessories_description": "accessories",
        "visual_style": "character style",
    }
    details.extend(f"{label}: {bible[key]}" for key, label in labels.items() if bible.get(key))
    for label, values in (
        ("appearance locks", character.appearance_lock_json),
        ("style locks", character.style_lock_json),
    ):
        if isinstance(values, dict) and values:
            details.append(
                f"{label}: " + ", ".join(f"{key}={value}" for key, value in sorted(values.items()))
            )
    return "; ".join(value for value in details if value)


def build_character_reference_input(
    character: Character, project: Project, bible: ProjectBible | None
) -> dict[str, Any]:
    visual_bible = bible.visual_bible if bible and isinstance(bible.visual_bible, dict) else {}
    style = _text(visual_bible.get("preset")) or "webtoon illustration"
    prompt = "\n".join(
        [
            "Create one canonical character reference sheet for a webtoon production pipeline.",
            (
                "Show one person only, full body or medium full-body framing, front and "
                "three-quarter views, clear face, stable hairstyle, neutral expression, "
                "simple clean background, even lighting, no text, no logos, no other people."
            ),
            f"Project genre: {project.genre}. Visual style: {style}.",
            f"Character identity and fixed appearance: {_character_line(character)}",
            (
                "Face shape, hair, eyes, body proportions, accessories, default outfit and "
                "rendering style are identity locks. Keep them unchanged in future scene images."
            ),
        ]
    )
    return CharacterReferenceProviderInput(
        character_id=character.id,
        project_id=project.id,
        name=character.name,
        prompt=prompt,
        character_revision=character.character_revision,
    ).model_dump(mode="json")


def build_scene_image_input(
    scene: Scene,
    project: Project,
    bible: ProjectBible | None,
    characters: list[Character],
) -> dict[str, Any]:
    script = scene.script if isinstance(scene.script, dict) else {}
    visual_prompt = _text(script.get("visual_prompt"))
    if not visual_prompt:
        raise ValueError("Scene has no visual prompt")
    narration = _text(script.get("narration"))
    visual_bible = bible.visual_bible if bible and isinstance(bible.visual_bible, dict) else {}
    style = _text(visual_bible.get("preset")) or "webtoon illustration"
    sections = [
        (
            "Create one finished webtoon scene image with no captions, "
            "speech bubbles, borders, or text."
        ),
        f"Project genre: {project.genre}.",
        f"Visual style: {style}.",
        f"Scene direction: {visual_prompt}",
    ]
    if narration:
        sections.append(f"Narrative context: {narration}")
    references = [
        ReferenceAssetInput(character_id=character.id, asset_id=character.reference_asset_id)
        for character in characters
        if character.reference_asset_id is not None
    ][:4]
    sections.append(
        "Preserve every supplied canonical character reference identity: face, hairstyle, "
        "eyes, proportions, accessories, default outfit and rendering style. Scene action "
        "and pose may vary."
    )
    if characters:
        sections.append(
            "Characters present in this scene: "
            + " | ".join(_character_line(character) for character in characters)
        )
    prompt = "\n".join(sections)
    validated = SceneImageProviderInput(
        scene_id=scene.id,
        episode_id=scene.episode_id,
        prompt=prompt,
        character_ids=[character.id for character in characters],
        reference_asset_ids=[item.asset_id for item in references],
        reference_assets=references,
    )
    return validated.model_dump(mode="json")
