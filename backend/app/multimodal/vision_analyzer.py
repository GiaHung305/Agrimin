"""Fail-closed boundary for a future evaluated vision analyzer."""

from __future__ import annotations

from app.core.config import settings
from app.multimodal.contracts import VisualAnalysisResult
from app.multimodal.image_validation import ValidatedChatImage


class VisionAnalyzerUnavailable(RuntimeError):
    pass


async def analyze_validated_images(
    images: list[ValidatedChatImage],
) -> VisualAnalysisResult:
    if not settings.vision_analysis_enabled:
        raise VisionAnalyzerUnavailable("vision analysis is disabled")
    # Intentionally fail closed until a champion passes the versioned image
    # evaluation set. No provider/model call is wired in this phase.
    raise VisionAnalyzerUnavailable("no evaluated vision analyzer is configured")
