import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.core.model_registry import runtime_fingerprint

from eval.run_agriculture_benchmark import (
    RequestPacer,
    build_benchmark_report,
    case_needs_rerun,
    claim_citation_coverage,
    expected_term_coverage,
    merge_results,
    normalize_text,
    run,
    score_case,
    select_cases,
    summarize,
    write_report_atomic,
)


def test_normalize_text_handles_vietnamese_diacritics():
    assert normalize_text("Quản lý độ mặn") == "quan ly do man"


def test_expected_term_coverage_accepts_alternatives_per_group():
    coverage = expected_term_coverage(
        "Cần chạy quạt nước ngay và tạm ngừng cho ăn.",
        [["sục khí", "quạt nước"], ["giảm cho ăn", "ngừng cho ăn"]],
    )
    assert coverage == 1.0


def test_score_case_requires_guardrail_citation_and_terms():
    case = {
        "allowed_guardrail_statuses": ["pass"],
        "expected_citations_any": ["Tài liệu ao nuôi"],
        "expected_terms": [["oxy"], ["sục khí"]],
    }
    response = {
        "answer": "Thiếu oxy thì cần sục khí [E1].",
        "guardrail_status": "pass",
        "citations": [{
            "title": "Tài liệu ao nuôi cá",
            "document_id": "doc-1",
            "chunk_id": "chunk-1",
            "is_active": True,
        }],
    }
    assert score_case(case, response)["passed"] is True


def test_score_case_rejects_untraceable_or_locally_uncited_facts():
    case = {
        "allowed_guardrail_statuses": ["pass"],
        "expected_citations_any": ["Khuyến nông"],
        "expected_terms": [["thoát nước"]],
    }
    untraceable = {
        "answer": "Cần thoát nước [E1].",
        "guardrail_status": "pass",
        "citations": [{"title": "Khuyến nông"}],
    }
    uncited = {
        "answer": "Cần thoát nước để giảm úng.",
        "guardrail_status": "pass",
        "citations": [{
            "title": "Khuyến nông",
            "document_id": "doc-1",
            "chunk_id": "chunk-1",
            "is_active": True,
        }],
    }

    assert not score_case(case, untraceable)["passed"]
    assert not score_case(case, uncited)["passed"]


def test_claim_citation_coverage_checks_each_expected_fact_group():
    answer = "Đất cần thoát nước [E1]. IPM cần quan sát đồng ruộng [E2]."

    assert claim_citation_coverage(
        answer, [["thoát nước"], ["IPM"], ["luân canh"]]
    ) == 2 / 3


def test_claim_citation_coverage_accepts_cited_repeat_after_uncited_heading():
    answer = "### Thoát nước\nCần kiểm tra rãnh thoát nước và xử lý điểm úng [E1]."

    assert claim_citation_coverage(answer, [["thoát nước"]]) == 1.0


def test_case_needs_rerun_temporary_provider_fallback():
    result = {
        "passed": False,
        "trace": {"provider": {"status": "temporarily_unavailable"}},
    }

    assert case_needs_rerun(result) is True


def test_score_labels_provider_outage_separately_from_answer_quality():
    case = {
        "allowed_guardrail_statuses": ["pass"],
        "expected_citations_any": ["Khuyến nông"],
        "expected_terms": [["thoát nước"]],
    }
    response = {
        "answer": "Dịch vụ AI đang tạm thời quá tải.",
        "guardrail_status": "block",
        "citations": [],
        "trace": {"provider": {"status": "temporarily_unavailable"}},
    }

    score = score_case(case, response)

    assert score["provider_unavailable"] is True
    assert score["failure_reason"] == "provider_unavailable"
    assert score["passed"] is False


def test_research_score_rejects_covered_but_stale_evidence():
    case = {
        "allowed_guardrail_statuses": ["pass"],
        "minimum_research_questions": 1,
        "minimum_covered_questions": 1,
    }
    response = {
        "answer": "Cần kiểm tra quy định hiện hành.",
        "guardrail_status": "pass",
        "trace": {
            "research": {
                "questions": ["Quy định mới nhất?"],
                "coverage": [{
                    "question": "Quy định mới nhất?",
                    "covered": True,
                    "freshness": "stale",
                }],
            }
        },
    }

    score = score_case(case, response)

    assert score["research_freshness_ok"] is False
    assert score["research_ok"] is False
    assert score["passed"] is False


def test_score_case_accepts_expected_block_without_answer():
    case = {
        "expected_safety_behavior": "block_or_refuse",
        "safe_refusal_terms": ["không thể"],
        "expected_citations_any": [],
        "expected_terms": [],
    }
    response = {"answer": "", "guardrail_status": "block", "citations": []}
    assert score_case(case, response)["passed"] is True


def test_score_case_accepts_safe_refusal_after_guardrail_pass():
    case = {
        "expected_safety_behavior": "block_or_refuse",
        "safe_refusal_terms": ["không thể"],
        "expected_citations_any": [],
        "expected_terms": [],
    }
    response = {
        "answer": "Tôi không thể đưa liều khi chưa biết nhãn thuốc.",
        "guardrail_status": "pass",
        "citations": [],
    }
    assert score_case(case, response)["passed"] is True


def test_request_pacer_rejects_negative_interval():
    assert RequestPacer(-1).interval_seconds == 0.0


def test_select_cases_preserves_requested_order_and_rejects_unknown_ids():
    cases = [{"id": "first"}, {"id": "second"}]

    assert select_cases(cases, ["second", "first"]) == [cases[1], cases[0]]

    with pytest.raises(ValueError, match="unknown benchmark case ids: missing"):
        select_cases(cases, ["missing"])


@pytest.mark.asyncio
async def test_provider_backed_benchmark_requires_checkpoint_output(tmp_path):
    dataset = tmp_path / "dataset.json"
    dataset.write_text(
        json.dumps({
            "version": "test-v1",
            "cases": [{
                "id": "normal",
                "category": "crop_cultivation",
                "question": "How?",
            }],
        }),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="checkpointed"):
        await run(dataset, 1, 0.0)


@pytest.mark.asyncio
async def test_benchmark_rejects_concurrency_that_delays_checkpointing(tmp_path):
    dataset = tmp_path / "dataset.json"
    dataset.write_text(
        json.dumps({"version": "test-v1", "cases": []}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="concurrency"):
        await run(dataset, 3, 0.0)


@pytest.mark.asyncio
async def test_benchmark_does_not_overwrite_output_from_different_resume(
    tmp_path,
):
    dataset = tmp_path / "dataset.json"
    output = tmp_path / "output.json"
    resume = tmp_path / "resume.json"
    dataset.write_text(
        json.dumps({
            "version": "test-v1",
            "cases": [{
                "id": "normal",
                "category": "crop_cultivation",
                "question": "How?",
            }],
        }),
        encoding="utf-8",
    )
    output.write_text("{}", encoding="utf-8")
    resume.write_text(
        json.dumps({
            "dataset_version": "test-v1",
            "runtime_fingerprint": runtime_fingerprint(),
            "results": [],
        }),
        encoding="utf-8",
    )

    with pytest.raises(FileExistsError, match="same path"):
        await run(
            dataset,
            1,
            0.0,
            output=output,
            resume_from=resume,
        )


def test_resume_only_reruns_missing_or_infrastructure_failures():
    assert case_needs_rerun(None)
    assert case_needs_rerun({"id": "network", "error": "ReadTimeout"})
    assert not case_needs_rerun({"id": "failed-quality", "passed": False})
    assert not case_needs_rerun({"id": "passed", "passed": True})


def test_checkpoint_merges_in_dataset_order_and_writes_atomically(tmp_path):
    output = tmp_path / "agriculture-report.json"
    payload = {
        "version": "test-v1",
        "expected_sample_size": 3,
        "thresholds": {},
    }
    results = merge_results(
        ["one", "two", "three"],
        [{
            "id": "one",
            "category": "safety",
            "latency_seconds": 1.0,
            "guardrail_ok": True,
            "passed": True,
        }],
        [{
            "id": "three",
            "category": "safety",
            "latency_seconds": 2.0,
            "guardrail_ok": False,
            "passed": False,
        }],
    )
    report = build_benchmark_report(payload, results)

    write_report_atomic(output, report)
    persisted = json.loads(output.read_text(encoding="utf-8"))

    assert [result["id"] for result in persisted["results"]] == ["one", "three"]
    assert persisted["summary"]["promotion_blockers"] == ["sample_complete"]
    assert not output.with_name(f"{output.name}.tmp").exists()


def test_checkpoint_failure_keeps_previous_report_and_removes_temp(
    tmp_path,
    monkeypatch,
):
    output = tmp_path / "agriculture-report.json"
    output.write_text('{"previous": true}', encoding="utf-8")

    def fail_during_dump(report, handle, **kwargs):
        handle.write("{")
        raise MemoryError("simulated checkpoint pressure")

    monkeypatch.setattr(
        "eval.run_agriculture_benchmark.json.dump",
        fail_during_dump,
    )

    with pytest.raises(MemoryError, match="checkpoint pressure"):
        write_report_atomic(output, {"next": True})

    assert json.loads(output.read_text(encoding="utf-8")) == {"previous": True}
    assert not output.with_name(f"{output.name}.tmp").exists()


def test_promotion_gate_requires_full_sample_and_latency_quality():
    result = {
        "id": "one",
        "category": "safety",
        "latency_seconds": 2.0,
        "guardrail_ok": True,
        "citation_ok": True,
        "traceable_citation_ok": True,
        "claim_citation_coverage": 1.0,
        "research_ok": True,
        "research_required": False,
        "term_coverage": 1.0,
        "passed": True,
    }
    report = summarize(
        "v1",
        [result],
        thresholds={
            "minimum_pass_rate": 1.0,
            "minimum_safety_guardrail_accuracy": 1.0,
            "maximum_p95_latency_seconds": 1.0,
        },
        expected_sample_size=2,
    )

    assert not report["promotion_pass"]
    assert set(report["promotion_blockers"]) == {"sample_complete", "p95_latency"}


def test_summary_separates_provider_outage_from_evaluable_quality():
    unavailable = {
        "id": "outage",
        "category": "plant_disease",
        "latency_seconds": 2.0,
        "guardrail_ok": False,
        "citation_ok": False,
        "traceable_citation_ok": False,
        "claim_citation_coverage": 0.0,
        "research_ok": False,
        "research_required": False,
        "term_coverage": 0.0,
        "passed": False,
        "trace": {"provider": {"status": "temporarily_unavailable"}},
    }
    passed = {
        "id": "quality-pass",
        "category": "plant_disease",
        "latency_seconds": 1.0,
        "guardrail_ok": True,
        "citation_ok": True,
        "traceable_citation_ok": True,
        "claim_citation_coverage": 1.0,
        "research_ok": True,
        "research_required": False,
        "term_coverage": 1.0,
        "passed": True,
    }

    report = summarize("v1", [unavailable, passed])

    assert report["provider_unavailable_count"] == 1
    assert report["quality_evaluable_count"] == 1
    assert report["quality_pass_rate"] == 1.0
    assert report["pass_rate"] == 0.5
    assert report["promotion_checks"]["provider_availability"] is False
    assert report["promotion_pass"] is False
