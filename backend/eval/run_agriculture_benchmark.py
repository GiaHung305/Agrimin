"""Deterministic benchmark over the canonical authenticated production SSE route."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import statistics
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eval.run_eval import (
    citation_matches,
    evaluation_question_id,
    get_supabase_token,
    invoke_production_chat,
)
from app.core.model_registry import runtime_fingerprint, runtime_versions


DEFAULT_DATASET = Path(__file__).with_name("agriculture_benchmark_v2.json")
_CITATION_MARKER = re.compile(r"\[E\d+\]", re.IGNORECASE)


class RequestPacer:
    """Space request starts so the canonical API rate limit is respected."""

    def __init__(self, interval_seconds: float) -> None:
        self.interval_seconds = max(0.0, interval_seconds)
        self._lock = asyncio.Lock()
        self._next_start = 0.0

    async def wait(self) -> None:
        async with self._lock:
            now = time.perf_counter()
            delay = max(0.0, self._next_start - now)
            if delay:
                await asyncio.sleep(delay)
            started = time.perf_counter()
            self._next_start = started + self.interval_seconds


def normalize_text(value: str | None) -> str:
    decomposed = unicodedata.normalize("NFD", str(value or "").casefold())
    without_marks = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return " ".join(without_marks.replace("đ", "d").split())


def expected_term_coverage(answer: str, groups: list[list[str]]) -> float:
    if not groups:
        return 1.0
    normalized_answer = normalize_text(answer)
    matched = sum(
        any(normalize_text(candidate) in normalized_answer for candidate in group)
        for group in groups
    )
    return matched / len(groups)


def _traceable_internal_citation(citation: Any) -> bool:
    return bool(
        isinstance(citation, dict)
        and citation.get("document_id")
        and citation.get("chunk_id")
        and citation.get("is_active") is True
    )


def claim_citation_coverage(answer: str, groups: list[list[str]]) -> float:
    """Measure whether each expected fact is locally accompanied by [E#]."""
    if not groups:
        return 1.0
    folded = answer.casefold()
    covered = 0
    for group in groups:
        positions: list[int] = []
        for candidate in group:
            folded_candidate = str(candidate).casefold()
            start = 0
            while folded_candidate and (
                position := folded.find(folded_candidate, start)
            ) >= 0:
                positions.append(position)
                start = position + len(folded_candidate)
        if any(
            _CITATION_MARKER.search(
                answer[max(0, position - 80) : position + 320]
            )
            for position in positions
        ):
            covered += 1
    return covered / len(groups)


def score_case(case: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    answer = str(response.get("answer") or "")
    safety_behavior = case.get("expected_safety_behavior")
    if safety_behavior == "block_or_refuse":
        status = response.get("guardrail_status")
        refused = any(
            normalize_text(term) in normalize_text(answer)
            for term in case.get("safe_refusal_terms") or []
        )
        guardrail_ok = status == "block" or (status == "pass" and refused)
        answer_ok = status == "block" or bool(answer.strip())
    else:
        allowed_statuses = set(case.get("allowed_guardrail_statuses") or ["pass"])
        guardrail_ok = response.get("guardrail_status") in allowed_statuses
        expect_answer = case.get("expect_answer", True)
        answer_ok = bool(answer.strip()) if expect_answer else True
    expected_citations = case.get("expected_citations_any") or []
    citations = response.get("citations") or []
    matching_citations = [
        citation
        for citation in citations
        if any(citation_matches(expected, [citation]) for expected in expected_citations)
    ]
    citation_ok = not expected_citations or bool(matching_citations)
    traceable_citation_ok = not expected_citations or any(
        _traceable_internal_citation(citation) for citation in matching_citations
    )
    term_coverage = expected_term_coverage(
        answer, case.get("expected_terms") or []
    )
    facts_ok = term_coverage >= float(case.get("minimum_term_coverage", 1.0))
    claim_coverage = claim_citation_coverage(
        answer, case.get("expected_terms") or []
    )
    claim_citations_ok = claim_coverage >= float(
        case.get(
            "minimum_claim_citation_coverage",
            1.0 if expected_citations else 0.0,
        )
    )
    research = (response.get("trace") or {}).get("research") or {}
    questions = research.get("questions") or []
    coverage = research.get("coverage") or []
    covered_items = [item for item in coverage if item.get("covered")]
    covered_questions = len(covered_items)
    research_freshness_ok = all(
        item.get("freshness") in {"not_required", "current"}
        for item in covered_items
    )
    research_ok = (
        len(questions) >= int(case.get("minimum_research_questions", 0))
        and covered_questions >= int(case.get("minimum_covered_questions", 0))
        and research_freshness_ok
        and not (
            case.get("require_no_evidence_conflicts", False)
            and research.get("contradictions")
        )
    )
    return {
        "guardrail_ok": guardrail_ok,
        "answer_ok": answer_ok,
        "citation_ok": citation_ok,
        "traceable_citation_ok": traceable_citation_ok,
        "claim_citation_coverage": round(claim_coverage, 4),
        "claim_citations_ok": claim_citations_ok,
        "term_coverage": round(term_coverage, 4),
        "research_ok": research_ok,
        "research_freshness_ok": research_freshness_ok,
        "research_required": bool(
            case.get("minimum_research_questions", 0)
            or case.get("minimum_covered_questions", 0)
        ),
        "research_question_count": len(questions),
        "covered_research_question_count": covered_questions,
        "passed": (
            guardrail_ok
            and answer_ok
            and citation_ok
            and traceable_citation_ok
            and facts_ok
            and claim_citations_ok
            and research_ok
        ),
    }


def select_cases(
    cases: list[dict[str, Any]], case_ids: list[str] | None
) -> list[dict[str, Any]]:
    """Select an explicit diagnostic subset without creating another API path."""
    requested = list(dict.fromkeys(case_ids or []))
    if not requested:
        return cases
    known = {str(case["id"]): case for case in cases}
    missing = [case_id for case_id in requested if case_id not in known]
    if missing:
        raise ValueError("unknown benchmark case ids: " + ", ".join(missing))
    return [known[case_id] for case_id in requested]


def merge_results(
    ordered_case_ids: list[str],
    previous_results: list[dict[str, Any]],
    new_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = {result["id"]: result for result in previous_results}
    merged.update({result["id"]: result for result in new_results})
    return [merged[case_id] for case_id in ordered_case_ids if case_id in merged]


def case_needs_rerun(result: dict[str, Any] | None) -> bool:
    """Resume missing/infrastructure failures, not substantive accuracy misses."""
    if result is None or bool(result.get("error")):
        return True
    provider = (result.get("trace") or {}).get("provider") or {}
    return provider.get("status") == "temporarily_unavailable"


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * quantile)))
    return ordered[index]


async def run_case(
    client: httpx.AsyncClient,
    token: str,
    semaphore: asyncio.Semaphore,
    pacer: RequestPacer,
    case: dict[str, Any],
) -> dict[str, Any]:
    queued_at = time.perf_counter()
    try:
        async with semaphore:
            await pacer.wait()
            started = time.perf_counter()
            response = await invoke_production_chat(client, token, case["question"])
        latency = time.perf_counter() - started
        score = score_case(case, response)
        return {
            "id": case["id"],
            "question_id": evaluation_question_id(case["question"]),
            "category": case["category"],
            "latency_seconds": round(latency, 2),
            "queue_seconds": round(started - queued_at, 2),
            "confidence": response.get("confidence"),
            "guardrail_status": response.get("guardrail_status"),
            "answer_excerpt": str(response.get("answer") or "")[:800],
            "answer": str(response.get("answer") or ""),
            "citations": response.get("citations") or [],
            "citation_titles": [item.get("title") for item in response.get("citations") or []],
            "trace": response.get("trace") or {},
            **score,
        }
    except Exception as exc:
        return {
            "id": case["id"],
            "question_id": evaluation_question_id(case["question"]),
            "category": case["category"],
            "latency_seconds": round(time.perf_counter() - queued_at, 2),
            "error": f"{type(exc).__name__}: {str(exc)[:300]}",
            "guardrail_ok": False,
            "answer_ok": False,
            "citation_ok": False,
            "traceable_citation_ok": False,
            "claim_citation_coverage": 0.0,
            "claim_citations_ok": False,
            "term_coverage": 0.0,
            "research_ok": False,
            "research_freshness_ok": False,
            "research_required": bool(
                case.get("minimum_research_questions", 0)
                or case.get("minimum_covered_questions", 0)
            ),
            "research_question_count": 0,
            "covered_research_question_count": 0,
            "passed": False,
        }


def summarize(
    version: str,
    results: list[dict[str, Any]],
    *,
    thresholds: dict[str, float] | None = None,
    expected_sample_size: int | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or {}
    total = len(results)
    latencies = [float(item["latency_seconds"]) for item in results]
    confidence_values = [
        float(item["confidence"])
        for item in results
        if item.get("confidence") is not None
    ]
    citation_cases = [item for item in results if item["category"] != "safety"]
    safety_cases = [item for item in results if item["category"] == "safety"]
    research_cases = [item for item in results if item.get("research_required")]
    categories: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in results:
        categories[item["category"]].append(item)

    pass_rate = (
        sum(bool(item["passed"]) for item in results) / total if total else 0.0
    )
    citation_match_rate = (
        sum(bool(item["citation_ok"]) for item in citation_cases)
        / len(citation_cases)
        if citation_cases
        else 1.0
    )
    traceable_citation_rate = (
        sum(bool(item["traceable_citation_ok"]) for item in citation_cases)
        / len(citation_cases)
        if citation_cases
        else 1.0
    )
    claim_citation_rate = (
        statistics.fmean(
            float(item["claim_citation_coverage"]) for item in citation_cases
        )
        if citation_cases
        else 1.0
    )
    research_success_rate = (
        sum(bool(item["research_ok"]) for item in research_cases)
        / len(research_cases)
        if research_cases
        else 1.0
    )
    safety_guardrail_accuracy = (
        sum(bool(item["guardrail_ok"]) for item in safety_cases)
        / len(safety_cases)
        if safety_cases
        else 1.0
    )
    p95_latency = percentile(latencies, 0.95)
    checks = {
        "sample_complete": expected_sample_size is None or total == expected_sample_size,
        "pass_rate": pass_rate >= float(thresholds.get("minimum_pass_rate", 0.0)),
        "citation_match_rate": citation_match_rate
        >= float(thresholds.get("minimum_citation_match_rate", 0.0)),
        "traceable_citation_rate": traceable_citation_rate
        >= float(thresholds.get("minimum_traceable_citation_rate", 0.0)),
        "claim_citation_rate": claim_citation_rate
        >= float(thresholds.get("minimum_claim_citation_rate", 0.0)),
        "research_success_rate": research_success_rate
        >= float(thresholds.get("minimum_research_success_rate", 0.0)),
        "safety_guardrail_accuracy": safety_guardrail_accuracy
        >= float(thresholds.get("minimum_safety_guardrail_accuracy", 0.0)),
        "p95_latency": p95_latency
        <= float(thresholds.get("maximum_p95_latency_seconds", float("inf"))),
    }
    return {
        "dataset_version": version,
        "total": total,
        "passed": sum(bool(item["passed"]) for item in results),
        "pass_rate": round(pass_rate, 4),
        "citation_match_rate": round(citation_match_rate, 4),
        "traceable_citation_rate": round(traceable_citation_rate, 4),
        "claim_citation_rate": round(claim_citation_rate, 4),
        "research_success_rate": round(research_success_rate, 4),
        "safety_guardrail_accuracy": round(safety_guardrail_accuracy, 4),
        "average_term_coverage": round(
            statistics.fmean(
                float(item["term_coverage"]) for item in citation_cases
            ),
            4,
        ) if citation_cases else 1.0,
        "average_confidence": round(
            statistics.fmean(confidence_values), 4
        ) if confidence_values else 0.0,
        "latency_seconds": {
            "p50": round(percentile(latencies, 0.50), 2),
            "p95": round(p95_latency, 2),
            "max": round(max(latencies), 2) if latencies else 0.0,
        },
        "categories": {
            category: {
                "passed": sum(bool(item["passed"]) for item in items),
                "total": len(items),
            }
            for category, items in sorted(categories.items())
        },
        "failures": [
            {
                key: item.get(key)
                for key in (
                    "id", "category", "error", "guardrail_status", "guardrail_ok",
                    "citation_ok", "traceable_citation_ok", "claim_citation_coverage",
                    "research_ok", "research_freshness_ok", "term_coverage",
                    "latency_seconds", "citation_titles",
                )
                if item.get(key) is not None
            }
            for item in results
            if not item["passed"]
        ],
        "promotion_checks": checks,
        "promotion_pass": all(checks.values()),
        "promotion_blockers": [
            name for name, passed in checks.items() if not passed
        ],
    }


def build_benchmark_report(
    payload: dict[str, Any], results: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "dataset_version": payload["version"],
        "runtime_fingerprint": runtime_fingerprint(),
        "runtime_versions": runtime_versions(),
        "summary": summarize(
            payload["version"],
            results,
            thresholds=payload.get("thresholds"),
            expected_sample_size=payload.get("expected_sample_size"),
        ),
        "results": results,
    }


def write_report_atomic(output: Path, report: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f"{output.name}.tmp")
    try:
        # Stream directly to disk instead of materializing a second full JSON
        # string. This keeps checkpoint memory bounded on the 8 GB pilot host.
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
        temporary.replace(output)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


async def run(
    dataset_path: Path,
    concurrency: int,
    request_interval_seconds: float,
    case_ids: list[str] | None = None,
    *,
    output: Path | None = None,
    resume_from: Path | None = None,
) -> dict[str, Any]:
    if concurrency not in {1, 2}:
        raise ValueError("benchmark concurrency must be 1 or 2")
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    all_cases = payload["cases"]
    ordered_case_ids = [str(case["id"]) for case in all_cases]
    previous_results: list[dict[str, Any]] = []
    if resume_from:
        previous_report = json.loads(resume_from.read_text(encoding="utf-8"))
        if previous_report.get("dataset_version") != payload["version"]:
            raise ValueError("resume report dataset version does not match")
        if previous_report.get("runtime_fingerprint") != runtime_fingerprint():
            raise ValueError("resume report runtime fingerprint does not match")
        previous_results = previous_report.get("results") or []
    previous_by_id = {result["id"]: result for result in previous_results}

    if case_ids:
        cases = select_cases(all_cases, case_ids)
    elif resume_from:
        cases = [
            case
            for case in all_cases
            if case_needs_rerun(previous_by_id.get(str(case["id"])))
        ]
    else:
        cases = all_cases

    provider_cases = [case for case in cases if case.get("category") != "safety"]
    if provider_cases and output is None:
        raise RuntimeError(
            "pass --output so provider-backed cases can be checkpointed"
        )
    if output and output.exists() and (
        not resume_from or output.resolve() != resume_from.resolve()
    ):
        raise FileExistsError(
            "existing output may only be continued from that same path"
        )

    semaphore = asyncio.Semaphore(max(1, concurrency))
    pacer = RequestPacer(request_interval_seconds)
    new_results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=240.0, limits=httpx.Limits(max_connections=max(2, concurrency))) as client:
        token = await get_supabase_token(client)
        batch_size = max(1, concurrency)
        for offset in range(0, len(cases), batch_size):
            batch = cases[offset : offset + batch_size]
            new_results.extend(await asyncio.gather(*(
                run_case(client, token, semaphore, pacer, case)
                for case in batch
            )))
            if output:
                checkpoint_results = merge_results(
                    ordered_case_ids, previous_results, new_results
                )
                write_report_atomic(
                    output,
                    build_benchmark_report(payload, checkpoint_results),
                )

    results = merge_results(
        ordered_case_ids, previous_results, new_results
    )
    report = build_benchmark_report(payload, results)
    if output:
        write_report_atomic(output, report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--concurrency", type=int, choices=(1, 2), default=1)
    parser.add_argument("--request-interval", type=float, default=7.0)
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resume-from", type=Path)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    report = asyncio.run(
        run(
            args.dataset,
            args.concurrency,
            args.request_interval,
            args.case_id,
            output=args.output,
            resume_from=args.resume_from,
        )
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
