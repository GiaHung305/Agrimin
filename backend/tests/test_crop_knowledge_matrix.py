from __future__ import annotations

import sys
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.farm_monitoring import POLICIES  # noqa: E402
from eval.build_crop_knowledge_matrix import build_report, load_registry  # noqa: E402


REGISTRY_PATH = BACKEND_ROOT / "eval" / "crop_knowledge_source_tags_v1.json"


def test_source_registry_is_complete_and_uses_supported_dimensions() -> None:
    registry = load_registry(REGISTRY_PATH)

    assert registry["version"] == "crop-knowledge-source-tags-v1"
    assert len(registry["sources"]) == 132
    assert len({rule["source"] for rule in registry["sources"]}) == 132
    assert len(registry["dimensions"]["topics"]) == 7
    assert len(registry["dimensions"]["stages"]) == 4
    assert len(registry["dimensions"]["regions"]) == 7


def test_matrix_distinguishes_generic_baseline_from_specific_coverage() -> None:
    registry = {
        "version": "test-v1",
        "dimensions": {
            "topics": ["cultivation", "food_safety"],
            "stages": ["initial", "development"],
            "regions": ["red_river_delta", "mekong_delta"],
        },
        "sources": [
            {
                "source": "generic",
                "source_type": "government",
                "crop_keys": [],
                "crop_groups": ["all_crops"],
                "topics": ["food_safety"],
                "stages": ["all"],
                "regions": ["national"],
                "count_for_coverage": True,
            },
            {
                "source": "rice-specific",
                "source_type": "government",
                "crop_keys": ["rice"],
                "crop_groups": [],
                "topics": ["cultivation"],
                "stages": ["initial"],
                "regions": ["red_river_delta"],
                "count_for_coverage": True,
            },
        ],
    }
    active = [
        {"source": "generic", "source_type": "government", "documents": 1},
        {"source": "rice-specific", "source_type": "government", "documents": 1},
    ]

    report = build_report(registry, active)
    rice = next(crop for crop in report["crops"] if crop["key"] == "rice")
    tomato = next(crop for crop in report["crops"] if crop["key"] == "tomato")

    assert len(report["crops"]) == len(POLICIES)
    assert rice["crop_specific_sources"] == 1
    assert rice["cells"] == {
        "covered": 1,
        "gap": 3,
        "baseline_only": 4,
        "total": 8,
    }
    assert tomato["crop_specific_sources"] == 0
    assert tomato["priority"] == "P0"
    assert tomato["cells"]["baseline_only"] == 4


def test_matrix_blocks_unclassified_active_source() -> None:
    registry = load_registry(REGISTRY_PATH)
    report = build_report(
        registry,
        [{"source": "not-reviewed", "source_type": "unknown", "documents": 1}],
    )

    codes = {blocker["code"] for blocker in report["blockers"]}
    assert "unclassified_active_sources" in codes
    assert "registered_sources_not_active" in codes


def test_registry_rejects_unknown_crop_key(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    path.write_text(
        '{"version":"x","dimensions":{"topics":["t"],"stages":["s"],'
        '"regions":["r"]},"sources":[{"source":"x","source_type":"x",'
        '"crop_keys":["not_a_crop"],"crop_groups":[],"topics":["t"],'
        '"stages":["s"],"regions":["r"],"count_for_coverage":true}]}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown_crop_keys"):
        load_registry(path)
