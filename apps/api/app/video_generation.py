from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

VIDEO_PROMPT_VERSION = "scene-motion-v1"
RUNWAY_RATIOS = ("1280:720", "720:1280", "1104:832", "832:1104", "960:960", "1584:672")


@dataclass(frozen=True)
class SceneMotionPrompt:
    prompt: str
    ratio: str
    version: str = VIDEO_PROMPT_VERSION


def closest_runway_ratio(width: int, height: int) -> str:
    """Choose the supported ratio with the least centered crop for the source image."""
    source = width / height

    def crop_loss(ratio: str) -> float:
        out_width, out_height = (int(part) for part in ratio.split(":"))
        target = out_width / out_height
        return abs(source - target) / max(source, target)

    return min(RUNWAY_RATIOS, key=crop_loss)


def compose_scene_motion_prompt(
    scene_id: UUID,
    narration: Any,
    visual_prompt: Any,
    character_ids: Any,
    *,
    width: int,
    height: int,
    duration_seconds: int = 5,
    character_context: list[str] | None = None,
) -> SceneMotionPrompt:
    context = " ".join(
        value.strip()[:220]
        for value in (narration, visual_prompt)
        if isinstance(value, str) and value.strip()
    )[:220]
    character_line = (
        "Preserve visible character identity and appearance: "
        + "; ".join(character_context[:4])[:160]
        if character_context
        else "Do not introduce any characters that are not already visible."
    )
    prompt = (
        f"Create a restrained {duration_seconds}-second webtoon motion preview from this exact "
        "first frame. "
        "Use only subtle breathing, a soft blink, slight hair or fabric movement, and a very "
        "slow camera push-in when appropriate to the scene. Preserve the exact character "
        "identity, face, hair, clothing, composition, and visual style of the source image. "
        "Keep the face, anatomy, costume, and background composition stable. Avoid strong "
        "camera movement, deformation, cuts, new objects, or new characters. "
        f"{character_line} Scene context: {context or 'quiet, minimal movement'}"
    )
    return SceneMotionPrompt(prompt, closest_runway_ratio(width, height))


def scene_motion_input(
    *,
    scene_id: UUID,
    episode_id: UUID,
    image_asset_id: UUID,
    prompt: str,
    width: int,
    height: int,
    model: str,
    duration_seconds: int,
    ratio: str,
) -> dict[str, Any]:
    return {
        "scene_id": str(scene_id),
        "episode_id": str(episode_id),
        "image_asset_id": str(image_asset_id),
        "prompt": prompt,
        "prompt_version": VIDEO_PROMPT_VERSION,
        "source_width": width,
        "source_height": height,
        "model": model,
        "duration_seconds": duration_seconds,
        "ratio": ratio,
    }
