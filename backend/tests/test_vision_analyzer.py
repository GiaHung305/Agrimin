import os
import sys
from types import SimpleNamespace

import pytest
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.multimodal import vision_analyzer
from app.multimodal.image_validation import ValidatedChatImage


def _validated_image(image_id: str = "0123456789abcdef") -> ValidatedChatImage:
    return ValidatedChatImage(
        raw_bytes=b"transient-image-bytes",
        observation={
            "image_id": image_id,
            "mime_type": "image/jpeg",
            "byte_size": 21,
            "width": 512,
            "height": 512,
            "quality_status": "pass",
            "quality_issues": [],
            "usable_for_vision": True,
            "mean_brightness": 100.0,
            "edge_variance": 50.0,
        },
    )


@pytest.mark.asyncio
async def test_gemini_vision_returns_typed_observations(monkeypatch):
    captured = {}

    async def fake_generate(role, contents, *, config):
        captured["role"] = role
        captured["contents"] = contents
        captured["config"] = config
        return SimpleNamespace(text="""{
          "observations": [{
            "image_id": "0123456789abcdef",
            "relevance": "agriculture_plant",
            "crop_candidate": "cà chua",
            "plant_part": "leaf",
            "visible_symptoms": [{
              "symptom_type": "spot",
              "description": "đốm nâu tròn rải rác trên phiến lá",
              "colors": ["brown"],
              "distribution": "scattered",
              "region": null,
              "confidence": 0.82
            }],
            "limitations": ["single_view"],
            "confidence": 0.78
          }]
        }""")

    monkeypatch.setattr(vision_analyzer.settings, "vision_analysis_enabled", True)
    monkeypatch.setattr(vision_analyzer.settings, "google_api_key", "test-key")
    monkeypatch.setattr(vision_analyzer, "generate_content", fake_generate)
    result = await vision_analyzer.analyze_validated_images([_validated_image()])
    assert result.analyzer_id.startswith("google:")
    assert result.observations[0].visible_symptoms[0].symptom_type == "spot"
    assert captured["role"] == vision_analyzer.ModelRole.VISION
    assert any(getattr(item, "inline_data", None) for item in captured["contents"])
    assert captured["config"].response_schema is not None
    assert "additionalProperties" not in str(captured["config"].response_schema)


@pytest.mark.asyncio
async def test_gemini_vision_rejects_diagnostic_language(monkeypatch):
    async def fake_generate(role, contents, *, config):
        return SimpleNamespace(text="""{
          "observations": [{
            "image_id": "0123456789abcdef",
            "relevance": "agriculture_plant",
            "crop_candidate": "cà chua",
            "plant_part": "leaf",
            "visible_symptoms": [{
              "symptom_type": "spot",
              "description": "bệnh do nấm gây ra",
              "colors": ["brown"],
              "distribution": "scattered",
              "confidence": 0.9
            }],
            "limitations": [],
            "confidence": 0.9
          }]
        }""")

    monkeypatch.setattr(vision_analyzer.settings, "vision_analysis_enabled", True)
    monkeypatch.setattr(vision_analyzer.settings, "google_api_key", "test-key")
    monkeypatch.setattr(vision_analyzer, "generate_content", fake_generate)
    with pytest.raises(ValueError, match="visual, not diagnostic"):
        await vision_analyzer.analyze_validated_images([_validated_image()])


@pytest.mark.asyncio
async def test_gemini_vision_requires_api_key(monkeypatch):
    monkeypatch.setattr(vision_analyzer.settings, "vision_analysis_enabled", True)
    monkeypatch.setattr(vision_analyzer.settings, "google_api_key", "")
    with pytest.raises(vision_analyzer.VisionAnalyzerUnavailable):
        await vision_analyzer.analyze_validated_images([_validated_image()])


@pytest.mark.asyncio
async def test_gemini_vision_supports_explicit_test_gate(monkeypatch):
    async def fake_generate(role, contents, *, config):
        return SimpleNamespace(text='''{
          "observations": [{
            "image_id": "0123456789abcdef",
            "relevance": "agriculture_plant",
            "crop_candidate": "tomato",
            "plant_part": "leaf",
            "visible_symptoms": [],
            "limitations": ["single_view"],
            "confidence": 0.8
          }]
        }''')

    monkeypatch.setattr(vision_analyzer.settings, "vision_analysis_enabled", False)
    monkeypatch.setattr(vision_analyzer.settings, "google_api_key", "test-key")
    monkeypatch.setattr(vision_analyzer, "generate_content", fake_generate)

    result = await vision_analyzer.analyze_validated_images(
        [_validated_image()], enabled=True
    )

    assert result.observations[0].crop_candidate == "tomato"
