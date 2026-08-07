import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from pydantic import ValidationError

from app.multimodal.contracts import (
    VisualAnalysisResult,
    VisualObservation,
    build_visual_retrieval_query,
    validate_analysis_image_scope,
)


DATASET_PATH = (
    Path(__file__).resolve().parents[1]
    / "eval"
    / "multimodal_contract_dataset_v1.json"
)


def _dataset() -> dict:
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _dataset()["cases"], ids=lambda case: case["id"])
def test_versioned_visual_observation_contract(case):
    if not case["expected_valid"]:
        with pytest.raises(ValidationError):
            VisualObservation.model_validate(case["observation"])
        return

    observation = VisualObservation.model_validate(case["observation"])
    query = build_visual_retrieval_query(case["base_question"], [observation])
    for term in case["expected_query_terms"]:
        assert term in query
    if not case["expected_query_terms"]:
        assert query == case["base_question"]


def test_visual_analysis_scope_must_match_validated_images():
    result = VisualAnalysisResult.model_validate({
        "schema_version": "visual-observation-v1",
        "analyzer_id": "fake-analyzer",
        "observations": [_dataset()["cases"][0]["observation"]],
    })
    validate_analysis_image_scope(result, {"0123456789abcdef"})
    with pytest.raises(ValueError, match="do not match"):
        validate_analysis_image_scope(result, {"ffffffffffffffff"})


def test_duplicate_analysis_image_ids_are_rejected_by_scope_check():
    observation = _dataset()["cases"][0]["observation"]
    result = VisualAnalysisResult.model_validate({
        "schema_version": "visual-observation-v1",
        "analyzer_id": "fake-analyzer",
        "observations": [observation, observation],
    })
    with pytest.raises(ValueError, match="duplicate"):
        validate_analysis_image_scope(result, {"0123456789abcdef"})
