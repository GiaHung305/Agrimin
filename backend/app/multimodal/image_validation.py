"""Safe, deterministic validation for transient chat images."""

from __future__ import annotations

import base64
import binascii
import hashlib
from dataclasses import dataclass
from io import BytesIO
from typing import Literal, TypedDict

from PIL import Image, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError

from app.core.config import settings

ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
_FORMAT_TO_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
_THUMBNAIL_SIZE = (256, 256)
_MIN_MEAN_BRIGHTNESS = 25.0
_MAX_MEAN_BRIGHTNESS = 235.0
_MIN_EDGE_VARIANCE = 18.0


class ImageObservation(TypedDict):
    image_id: str
    mime_type: str
    byte_size: int
    width: int
    height: int
    quality_status: Literal["pass", "needs_retake"]
    quality_issues: list[str]
    usable_for_vision: bool
    mean_brightness: float
    edge_variance: float


class ImageValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedChatImage:
    """Transient raw bytes plus the only metadata allowed into graph state."""

    raw_bytes: bytes
    observation: ImageObservation


def _decode_base64(data_base64: str) -> bytes:
    try:
        raw = base64.b64decode(data_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ImageValidationError("Ảnh không có dữ liệu base64 hợp lệ.") from exc
    if not raw:
        raise ImageValidationError("Ảnh không được để trống.")
    if len(raw) > settings.max_chat_image_bytes:
        max_mb = settings.max_chat_image_bytes // (1024 * 1024)
        raise ImageValidationError(f"Mỗi ảnh phải nhỏ hơn hoặc bằng {max_mb} MB.")
    return raw


def _quality_metrics(image: Image.Image) -> tuple[float, float]:
    grayscale = image.convert("L")
    grayscale.thumbnail(_THUMBNAIL_SIZE)
    brightness = float(ImageStat.Stat(grayscale).mean[0])
    edges = grayscale.filter(ImageFilter.FIND_EDGES)
    if edges.width > 4 and edges.height > 4:
        edges = edges.crop((2, 2, edges.width - 2, edges.height - 2))
    edge_variance = float(ImageStat.Stat(edges).var[0])
    return round(brightness, 2), round(edge_variance, 2)


def validate_chat_image_payload(
    data_base64: str, claimed_mime_type: str
) -> ValidatedChatImage:
    if claimed_mime_type not in ALLOWED_IMAGE_MIME_TYPES:
        raise ImageValidationError("Chỉ hỗ trợ ảnh JPEG, PNG hoặc WebP.")

    raw = _decode_base64(data_base64)
    try:
        with Image.open(BytesIO(raw)) as probe:
            actual_mime_type = _FORMAT_TO_MIME.get(probe.format or "")
            if actual_mime_type is None:
                raise ImageValidationError("Định dạng ảnh không được hỗ trợ.")
            if actual_mime_type != claimed_mime_type:
                raise ImageValidationError("MIME khai báo không khớp nội dung ảnh.")
            width, height = probe.size
            if width * height > settings.max_chat_image_pixels:
                raise ImageValidationError("Ảnh có số pixel vượt giới hạn an toàn.")
            probe.verify()

        with Image.open(BytesIO(raw)) as decoded:
            frame_count = int(getattr(decoded, "n_frames", 1))
            if frame_count != 1:
                raise ImageValidationError("Không hỗ trợ ảnh động hoặc ảnh nhiều khung.")
            image = ImageOps.exif_transpose(decoded).copy()
    except ImageValidationError:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError) as exc:
        raise ImageValidationError("Không thể giải mã ảnh an toàn.") from exc

    width, height = image.size

    brightness, edge_variance = _quality_metrics(image)
    issues: list[str] = []
    if min(width, height) < settings.min_chat_image_dimension:
        issues.append("low_resolution")
    if brightness < _MIN_MEAN_BRIGHTNESS:
        issues.append("too_dark")
    elif brightness > _MAX_MEAN_BRIGHTNESS:
        issues.append("overexposed")
    if edge_variance < _MIN_EDGE_VARIANCE:
        issues.append("blurry_or_low_detail")

    observation: ImageObservation = {
        "image_id": hashlib.sha256(raw).hexdigest()[:16],
        "mime_type": claimed_mime_type,
        "byte_size": len(raw),
        "width": width,
        "height": height,
        "quality_status": "needs_retake" if issues else "pass",
        "quality_issues": issues,
        "usable_for_vision": not issues,
        "mean_brightness": brightness,
        "edge_variance": edge_variance,
    }
    return ValidatedChatImage(raw_bytes=raw, observation=observation)


def validate_chat_image(data_base64: str, claimed_mime_type: str) -> ImageObservation:
    """Backward-compatible metadata-only validation helper."""
    return validate_chat_image_payload(data_base64, claimed_mime_type).observation
