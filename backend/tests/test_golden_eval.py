import json
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eval.run_eval import (
    JudgeScore,
    build_eval_report,
    eval_item_needs_rerun,
    evaluation_question_id,
    evaluation_gate,
    merge_eval_results,
    run_eval,
    reusable_response_map,
    write_eval_report_atomic,
)
from eval.seed_golden_dataset import dataset_path
from app.core.model_registry import runtime_fingerprint


def test_default_v2_golden_dataset_is_versioned_and_has_no_mock_sources():
    payload = json.loads(dataset_path("v2").read_text(encoding="utf-8"))

    assert payload["version"] == "v2"
    assert len(payload["items"]) >= 10
    serialized = json.dumps(payload, ensure_ascii=False).casefold()
    assert "tai lieu mau" not in serialized
    assert "mock_source" not in serialized


def test_every_golden_v2_question_can_reuse_the_20_case_benchmark_response():
    golden = json.loads(dataset_path("v2").read_text(encoding="utf-8"))
    agriculture = json.loads(
        (dataset_path("v2").with_name("agriculture_benchmark_v2.json"))
        .read_text(encoding="utf-8")
    )
    agriculture_ids = {
        evaluation_question_id(case["question"])
        for case in agriculture["cases"]
    }

    assert all(
        evaluation_question_id(item["question"]) in agriculture_ids
        for item in golden["items"]
    )


def test_golden_evaluation_gate_requires_citations_and_perfect_safety():
    assert evaluation_gate(
        accuracy=0.90,
        citation_score=0.90,
        guardrail_accuracy=1.0,
    )["passed"]
    assert not evaluation_gate(
        accuracy=0.90,
        citation_score=0.79,
        guardrail_accuracy=1.0,
    )["passed"]
    assert not evaluation_gate(
        accuracy=0.90,
        citation_score=0.90,
        guardrail_accuracy=0.99,
    )["passed"]


def test_judge_score_is_typed_and_bounded():
    assert JudgeScore.model_validate({"score": 0.75}).score == 0.75


def test_golden_resume_only_reruns_missing_or_provider_errors():
    assert eval_item_needs_rerun(None)
    assert eval_item_needs_rerun({"item_id": "one", "error": "ReadTimeout"})
    assert not eval_item_needs_rerun({"item_id": "one", "judge_score": 0.2})
    assert not eval_item_needs_rerun({"item_id": "one", "guardrail_ok": False})


@pytest.mark.asyncio
async def test_golden_eval_requires_checkpoint_output_before_database_access():
    with pytest.raises(RuntimeError, match="checkpointed"):
        await run_eval()


@pytest.mark.asyncio
async def test_golden_eval_does_not_overwrite_output_from_different_resume(tmp_path):
    output = tmp_path / "output.json"
    resume = tmp_path / "resume.json"
    output.write_text("{}", encoding="utf-8")
    resume.write_text("{}", encoding="utf-8")

    with pytest.raises(FileExistsError, match="same path"):
        await run_eval(output=output, resume_from=resume)


def test_golden_checkpoint_is_atomic_and_partial_sample_cannot_pass(tmp_path):
    questions = [
        SimpleNamespace(
            id="one",
            category="normal",
            expected_answer="Expected fact",
            expected_citation="Official source",
        ),
        SimpleNamespace(
            id="two",
            category="guardrail",
            expected_answer="BLOCKED - unsafe",
            expected_citation=None,
        ),
    ]
    results = merge_eval_results(
        ["one", "two"],
        [],
        [{
            "item_id": "one",
            "category": "normal",
            "guardrail_test": False,
            "judge_score": 0.9,
            "citation_ok": True,
        }],
    )
    report = build_eval_report(questions, results)
    output = tmp_path / "golden-report.json"

    write_eval_report_atomic(output, report)
    persisted = json.loads(output.read_text(encoding="utf-8"))

    assert persisted["summary"]["complete"] == 1
    assert not persisted["summary"]["passed"]
    assert not persisted["summary"]["gate"]["checks"]["sample_complete"]
    assert not output.with_name(f"{output.name}.tmp").exists()


def test_reusable_response_map_requires_same_fingerprint_and_full_payload():
    questions = [SimpleNamespace(question="Question one")]
    question_id = evaluation_question_id("Question one")
    report = {
        "runtime_fingerprint": runtime_fingerprint(),
        "results": [{
            "question_id": question_id,
            "answer": "Answer",
            "citations": [],
            "guardrail_status": "pass",
        }],
    }

    reused = reusable_response_map(report, questions)

    assert reused[question_id]["answer"] == "Answer"
    report["results"][0].pop("citations")
    with pytest.raises(ValueError, match="reusable answer/citation"):
        reusable_response_map(report, questions)
