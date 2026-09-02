import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eval.migrate_qdrant_crop_scope import (
    crop_scope_for_payload,
    evidence_scope_for_payload,
    load_source_crop_keys,
    load_source_scopes,
)


def test_source_registry_scope_merges_duplicate_source_entries(tmp_path: Path):
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({
        "sources": [
            {"source": "https://example.gov/a", "crop_keys": ["rice"]},
            {"source": "https://example.gov/a", "crop_keys": ["banana"]},
        ]
    }), encoding="utf-8")

    assert load_source_crop_keys(registry) == {
        "https://example.gov/a": ["banana", "rice"]
    }


def test_existing_point_scope_wins_over_source_level_fallback():
    mapping = {"https://example.gov/a": ["banana", "rice"]}

    assert crop_scope_for_payload(
        {"source": "https://example.gov/a", "crop_keys": ["tomato"]},
        mapping,
    ) == ["tomato"]
    assert crop_scope_for_payload(
        {"source": "https://example.gov/a"},
        mapping,
    ) == ["banana", "rice"]


def test_source_registry_merges_all_reviewed_scope_dimensions(tmp_path: Path):
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({
        "sources": [
            {
                "source": "https://example.gov/a",
                "crop_keys": ["rice"],
                "stages": ["development"],
                "regions": ["mekong_delta"],
            },
            {
                "source": "https://example.gov/a",
                "crop_keys": ["banana"],
                "stages": ["late_season"],
                "regions": ["national"],
            },
        ]
    }), encoding="utf-8")

    assert load_source_scopes(registry) == {
        "https://example.gov/a": {
            "crop_keys": ["banana", "rice"],
            "stages": ["development", "late_season"],
            "regions": ["mekong_delta", "national"],
        }
    }


def test_existing_dimension_wins_without_hiding_other_reviewed_dimensions():
    scopes = {
        "https://example.gov/a": {
            "crop_keys": ["rice"],
            "stages": ["development"],
            "regions": ["mekong_delta"],
        }
    }

    assert evidence_scope_for_payload(
        {
            "source": "https://example.gov/a",
            "stages": ["late_season"],
        },
        scopes,
    ) == {
        "crop_keys": ["rice"],
        "stages": ["late_season"],
        "regions": ["mekong_delta"],
    }
