"""Checkpointed evaluation of AgriMind's production reflection contract."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import settings
from app.core.model_registry import model_name, runtime_fingerprint, runtime_versions
from app.core.model_registry import ModelRole
from app.services.model_gateway import ModelProviderUnavailable
from app.workflow.nodes.reflection import reflection_node


DEFAULT_DATASET = Path(__file__).with_name(
    "citation_entailment_benchmark_v1.json"
)
_VALID_STATUSES = {"sufficient", "need_more_search"}


def load_dataset(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases") or []
    expected_size = int(payload.get("expected_sample_size", -1))
    if expected_size != len(cases):
        raise ValueError(
            "expected_sample_size does not match the number of benchmark cases"
        )
    case_ids = [str(case.get("id") or "") for case in cases]
    if not all(case_ids) or len(set(case_ids)) != len(case_ids):
        raise ValueError("benchmark case ids must be non-empty and unique")
    for case in cases:
        if case.get("expected_status") not in _VALID_STATUSES:
            raise ValueError(
                f"invalid expected_status for case {case['id']}"
            )
        if not str(case.get("question") or "").strip():
            raise ValueError(f"missing question for case {case['id']}")
        if not str(case.get("answer") or "").strip():
            raise ValueError(f"missing answer for case {case['id']}")
        if not isinstance(case.get("evidence"), list):
            raise ValueError(f"missing evidence for case {case['id']}")
    return payload


def select_cases(
    cases: list[dict[str, Any]], case_ids: list[str] | None
) -> list[dict[str, Any]]:
    requested = list(dict.fromkeys(case_ids or []))
    if not requested:
        return cases
    known = {str(case["id"]): case for case in cases}
    missing = [case_id for case_id in requested if case_id not in known]
    if missing:
        raise ValueError("unknown benchmark case ids: " + ", ".join(missing))
    return [known[case_id] for case_id in requested]


def score_case(
    case: dict[str, Any], state: dict[str, Any]
) -> dict[str, Any]:
    actual_status = state.get("reflection_notes")
    unsupported_detected = bool(
        state.get("context", {}).get("claim_entailment_failed", False)
    )
    expected_unsupported = bool(case.get("expect_unsupported_claims", False))
    status_ok = actual_status == case["expected_status"]
    unsupported_detection_ok = unsupported_detected == expected_unsupported
    return {
        "actual_status": actual_status,
        "unsupported_claim_detected": unsupported_detected,
        "unsupported_claim_count": int(
            state.get("context", {}).get("unsupported_claim_count", 0)
        ),
        "status_ok": status_ok,
        "unsupported_detection_ok": unsupported_detection_ok,
        "passed": status_ok and unsupported_detection_ok,
    }


def summarize(
    dataset_version: str,
    results: list[dict[str, Any]],
    *,
    thresholds: dict[str, float],
    expected_sample_size: int,
) -> dict[str, Any]:
    expected_supported = [
        result
        for result in results
        if result.get("expected_status") == "sufficient"
    ]
    expected_unsupported = [
        result
        for result in results
        if result.get("expected_status") == "need_more_search"
    ]

    def rate(items: list[dict[str, Any]], predicate) -> float:
        if not items:
            return 0.0
        return sum(bool(predicate(item)) for item in items) / len(items)

    accuracy = sum(bool(result.get("passed")) for result in results) / max(
        expected_sample_size, 1
    )
    supported_acceptance = rate(
        expected_supported,
        lambda result: result.get("actual_status") == "sufficient",
    )
    unsupported_recall = rate(
        expected_unsupported,
        lambda result: result.get("actual_status") == "need_more_search",
    )
    unsupported_detection = rate(
        expected_unsupported,
        lambda result: result.get("unsupported_claim_detected") is True,
    )
    sample_complete = (
        len(results) == expected_sample_size
        and all(not result.get("error") for result in results)
    )
    metrics = {
        "accuracy": round(accuracy, 4),
        "supported_acceptance_rate": round(supported_acceptance, 4),
        "unsupported_recall": round(unsupported_recall, 4),
        "unsupported_claim_detection_rate": round(
            unsupported_detection, 4
        ),
    }
    blockers = []
    if not sample_complete:
        blockers.append("sample_complete")
    for metric_name, threshold_name in (
        ("accuracy", "minimum_accuracy"),
        ("supported_acceptance_rate", "minimum_supported_acceptance_rate"),
        ("unsupported_recall", "minimum_unsupported_recall"),
        (
            "unsupported_claim_detection_rate",
            "minimum_unsupported_claim_detection_rate",
        ),
    ):
        if metrics[metric_name] < float(thresholds[threshold_name]):
            blockers.append(metric_name)
    return {
        "dataset_version": dataset_version,
        "expected_sample_size": expected_sample_size,
        "completed_sample_size": len(results),
        "sample_complete": sample_complete,
        "metrics": metrics,
        "thresholds": thresholds,
        "promotion_pass": not blockers,
        "promotion_blockers": blockers,
    }


def build_report(
    dataset: dict[str, Any],
    results: list[dict[str, Any]],
    *,
    expected_sample_size: int,
) -> dict[str, Any]:
    return {
        "dataset_version": dataset["version"],
        "runtime_fingerprint": runtime_fingerprint(),
        "runtime_versions": runtime_versions(),
        "reflection_model": model_name(ModelRole.REFLECTION),
        "summary": summarize(
            dataset["version"],
            results,
            thresholds=dataset["thresholds"],
            expected_sample_size=expected_sample_size,
        ),
        "results": results,
    }


def write_report_atomic(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


async def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    state: dict[str, Any] = {
        "question": case["question"],
        "draft_answer": case["answer"],
        "answer_evidence": case["evidence"],
        "retrieved_docs": case["evidence"],
        "context": {},
        "retry_count": 0,
        "research_questions": [],
        "research_coverage": [],
        "missing_evidence": [],
        "evidence_conflicts": [],
        "research_stop_reason": None,
    }
    started = time.perf_counter()
    try:
        result = await reflection_node(state)
    except ModelProviderUnavailable as exc:
        return {
            "id": case["id"],
            "category": case["category"],
            "expected_status": case["expected_status"],
            "expect_unsupported_claims": case["expect_unsupported_claims"],
            "latency_seconds": round(time.perf_counter() - started, 2),
            "error": type(exc).__name__,
            "reason_code": exc.reason_code,
            "passed": False,
        }
    return {
        "id": case["id"],
        "category": case["category"],
        "expected_status": case["expected_status"],
        "expect_unsupported_claims": case["expect_unsupported_claims"],
        "latency_seconds": round(time.perf_counter() - started, 2),
        **score_case(case, result),
    }


def case_needs_rerun(result: dict[str, Any] | None) -> bool:
    return result is None or bool(result.get("error"))


async def run(
    dataset_path: Path,
    *,
    output: Path,
    case_ids: list[str] | None = None,
    delay_seconds: float | None = None,
    resume_from: Path | None = None,
) -> dict[str, Any]:
    dataset = load_dataset(dataset_path)
    selected = select_cases(dataset["cases"], case_ids)
    expected_size = len(selected)
    if delay_seconds is None:
        delay_seconds = settings.eval_request_delay_seconds
    delay_seconds = max(float(delay_seconds), 0.0)

    previous_results: dict[str, dict[str, Any]] = {}
    if resume_from is not None:
        if output.resolve() != resume_from.resolve():
            raise ValueError("resume_from and output must be the same path")
        previous = json.loads(resume_from.read_text(encoding="utf-8"))
        if previous.get("dataset_version") != dataset["version"]:
            raise ValueError("resume dataset version does not match")
        if previous.get("runtime_fingerprint") != runtime_fingerprint():
            raise ValueError("resume runtime fingerprint does not match")
        previous_results = {
            str(result["id"]): result for result in previous.get("results", [])
        }
    elif output.exists():
        raise FileExistsError(
            "output already exists; pass --resume-from with the same path"
        )

    ordered_ids = [str(case["id"]) for case in selected]
    completed = dict(previous_results)
    pending = [
        case
        for case in selected
        if case_needs_rerun(completed.get(str(case["id"])))
    ]
    for index, case in enumerate(pending):
        if index and delay_seconds:
            await asyncio.sleep(delay_seconds)
        result = await evaluate_case(case)
        completed[str(case["id"])] = result
        ordered_results = [
            completed[case_id]
            for case_id in ordered_ids
            if case_id in completed
        ]
        report = build_report(
            dataset,
            ordered_results,
            expected_sample_size=expected_size,
        )
        write_report_atomic(output, report)
        if result.get("error"):
            break

    ordered_results = [
        completed[case_id] for case_id in ordered_ids if case_id in completed
    ]
    report = build_report(
        dataset,
        ordered_results,
        expected_sample_size=expected_size,
    )
    write_report_atomic(output, report)
    return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case-id", action="append", dest="case_ids")
    parser.add_argument("--delay-seconds", type=float)
    parser.add_argument("--resume-from", type=Path)
    return parser.parse_args()


async def _main() -> None:
    args = _parse_args()
    report = await run(
        args.dataset,
        output=args.output,
        case_ids=args.case_ids,
        delay_seconds=args.delay_seconds,
        resume_from=args.resume_from,
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
