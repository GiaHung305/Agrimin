import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eval.run_agriculture_benchmark import (
    RequestPacer,
    expected_term_coverage,
    normalize_text,
    score_case,
    select_cases,
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
        "answer": "Thiếu oxy thì cần sục khí.",
        "guardrail_status": "pass",
        "citations": [{"title": "Tài liệu ao nuôi cá"}],
    }
    assert score_case(case, response)["passed"] is True


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

    import pytest

    with pytest.raises(ValueError, match="unknown benchmark case ids: missing"):
        select_cases(cases, ["missing"])
