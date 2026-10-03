"""Shared validation for uploaded and provider-generated image bytes."""

import warnings
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from app.errors import ApplicationError

MIME_FORMAT = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}
MAX_IMAGE_PIXELS = 25_000_000


def validate_video_bytes(content: bytes, mime_type: str, *, max_bytes: int) -> None:
    if not content or len(content) > max_bytes:
        raise ApplicationError("Video exceeds the configured size limit", "video_too_large", 413)
    if mime_type != "video/mp4":
        raise ApplicationError("Video must use MP4 format", "invalid_video_content_type", 415)
    # ISO Base Media File Format starts with a box header whose type is commonly `ftyp`.
    if len(content) < 12 or b"ftyp" not in content[:32]:
        raise ApplicationError("Video is not a valid MP4 container", "invalid_video", 415)


def validate_image_bytes(
    content: bytes,
    mime_type: str,
    *,
    max_bytes: int,
) -> tuple[int, int]:
    """Validate size, media type, static image format and decoded dimensions."""
    if not content or len(content) > max_bytes:
        raise ApplicationError("Images must be 10 MB or smaller", "file_too_large", 413)
    expected_format = MIME_FORMAT.get(mime_type)
    if expected_format is None:
        raise ApplicationError("File must be a PNG, JPEG or WebP image", "invalid_file_type", 415)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                if image.format != expected_format:
                    raise ValueError("Image content does not match the declared type")
                if getattr(image, "n_frames", 1) != 1:
                    raise ValueError("Only static images are supported")
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise ValueError("Image exceeds the pixel limit")
                width, height = image.size
                image.verify()
            with Image.open(BytesIO(content)) as image:
                image.load()
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
    return width, height
