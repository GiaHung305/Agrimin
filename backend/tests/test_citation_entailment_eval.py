import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from eval import run_citation_entailment_eval as evaluator


def test_versioned_dataset_is_balanced_and_complete():
    dataset = evaluator.load_dataset(evaluator.DEFAULT_DATASET)

    assert dataset["version"] == "citation-entailment-v1"
    assert dataset["expected_sample_size"] == len(dataset["cases"]) == 8
    assert sum(
        case["expected_status"] == "sufficient"
        for case in dataset["cases"]
    ) == 4
    assert sum(
        case["expected_status"] == "need_more_search"
        for case in dataset["cases"]
    ) == 4


def test_score_requires_status_and_unsupported_claim_signal():
    case = {
        "expected_status": "need_more_search",
        "expect_unsupported_claims": True,
    }
    state = {
        "reflection_notes": "need_more_search",
        "context": {
            "claim_entailment_failed": True,
            "unsupported_claim_count": 1,
        },
    }

    assert evaluator.score_case(case, state)["passed"] is True
    state["context"].clear()
    score = evaluator.score_case(case, state)
    assert score["status_ok"] is True
    assert score["unsupported_detection_ok"] is False
    assert score["passed"] is False


def test_summary_blocks_promotion_when_one_unsupported_claim_is_missed():
    results = [
        {
            "expected_status": "sufficient",
            "actual_status": "sufficient",
            "unsupported_claim_detected": False,
            "passed": True,
        },
        {
            "expected_status": "need_more_search",
            "actual_status": "sufficient",
            "unsupported_claim_detected": False,
            "passed": False,
        },
    ]
    summary = evaluator.summarize(
        "test-v1",
        results,
        thresholds={
            "minimum_accuracy": 0.5,
            "minimum_supported_acceptance_rate": 1.0,
            "minimum_unsupported_recall": 1.0,
            "minimum_unsupported_claim_detection_rate": 1.0,
        },
        expected_sample_size=2,
    )

    assert summary["sample_complete"] is True
    assert summary["metrics"]["accuracy"] == 0.5
    assert summary["metrics"]["unsupported_recall"] == 0.0
    assert summary["promotion_pass"] is False
    assert "unsupported_recall" in summary["promotion_blockers"]


@pytest.mark.asyncio
async def test_evaluate_case_uses_production_reflection_node(monkeypatch):
    async def fake_reflection(state):
        state["reflection_notes"] = "need_more_search"
        state["context"]["claim_entailment_failed"] = True
        state["context"]["unsupported_claim_count"] = 1
        return state

    monkeypatch.setattr(evaluator, "reflection_node", fake_reflection)
    case = {
        "id": "unsupported",
        "category": "test",
        "question": "Hỏi",
        "answer": "Claim [E1].",
        "evidence": [{"source": "Nguồn", "content": "Không hỗ trợ"}],
        "expected_status": "need_more_search",
        "expect_unsupported_claims": True,
    }

    result = await evaluator.evaluate_case(case)

    assert result["passed"] is True
    assert result["unsupported_claim_count"] == 1


@pytest.mark.asyncio
async def test_run_checkpoints_each_case_in_dataset_order(tmp_path, monkeypatch):
    dataset_path = tmp_path / "dataset.json"
    output = tmp_path / "report.json"
    dataset_path.write_text(
        json.dumps({
            "version": "test-v1",
            "expected_sample_size": 2,
            "thresholds": {
                "minimum_accuracy": 1.0,
                "minimum_supported_acceptance_rate": 1.0,
                "minimum_unsupported_recall": 1.0,
                "minimum_unsupported_claim_detection_rate": 1.0,
            },
            "cases": [
                {
                    "id": "supported",
                    "category": "test",
                    "question": "Hỏi 1",
                    "answer": "Đúng [E1].",
                    "evidence": [],
                    "expected_status": "sufficient",
                    "expect_unsupported_claims": False,
                },
                {
                    "id": "unsupported",
                    "category": "test",
                    "question": "Hỏi 2",
                    "answer": "Sai [E1].",
                    "evidence": [],
                    "expected_status": "need_more_search",
                    "expect_unsupported_claims": True,
                },
            ],
        }),
        encoding="utf-8",
    )

    async def fake_evaluate(case):
        unsupported = case["expect_unsupported_claims"]
        return {
            "id": case["id"],
            "category": case["category"],
            "expected_status": case["expected_status"],
            "expect_unsupported_claims": unsupported,
            "actual_status": case["expected_status"],
            "unsupported_claim_detected": unsupported,
            "unsupported_claim_count": int(unsupported),
            "status_ok": True,
            "unsupported_detection_ok": True,
            "passed": True,
        }

    monkeypatch.setattr(evaluator, "evaluate_case", fake_evaluate)
    report = await evaluator.run(
        dataset_path,
        output=output,
        delay_seconds=0,
    )

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert [result["id"] for result in persisted["results"]] == [
        "supported",
        "unsupported",
    ]
    assert report["summary"]["promotion_pass"] is True
    assert not output.with_name(f"{output.name}.tmp").exists()
