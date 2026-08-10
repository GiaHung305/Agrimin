"""Deterministic benchmark over the canonical authenticated production SSE route."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eval.run_eval import citation_matches, get_supabase_token, invoke_production_chat


DEFAULT_DATASET = Path(__file__).with_name("agriculture_benchmark_v2.json")


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
    citation_ok = not expected_citations or any(
        citation_matches(expected, response.get("citations") or [])
        for expected in expected_citations
    )
    term_coverage = expected_term_coverage(
        answer, case.get("expected_terms") or []
    )
    facts_ok = term_coverage >= float(case.get("minimum_term_coverage", 1.0))
    return {
        "guardrail_ok": guardrail_ok,
        "answer_ok": answer_ok,
        "citation_ok": citation_ok,
        "term_coverage": round(term_coverage, 4),
        "passed": guardrail_ok and answer_ok and citation_ok and facts_ok,
    }


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
            "category": case["category"],
            "latency_seconds": round(latency, 2),
            "queue_seconds": round(started - queued_at, 2),
            "confidence": response.get("confidence"),
            "guardrail_status": response.get("guardrail_status"),
            "answer_excerpt": str(response.get("answer") or "")[:800],
            "citation_titles": [item.get("title") for item in response.get("citations") or []],
            **score,
        }
    except Exception as exc:
        return {
            "id": case["id"],
            "category": case["category"],
            "latency_seconds": round(time.perf_counter() - queued_at, 2),
            "error": f"{type(exc).__name__}: {str(exc)[:300]}",
            "guardrail_ok": False,
            "answer_ok": False,
            "citation_ok": False,
            "term_coverage": 0.0,
            "passed": False,
        }


def summarize(version: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    latencies = [float(item["latency_seconds"]) for item in results]
    confidence_values = [
        float(item["confidence"])
        for item in results
        if item.get("confidence") is not None
    ]
    citation_cases = [item for item in results if item["category"] != "safety"]
    safety_cases = [item for item in results if item["category"] == "safety"]
    categories: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in results:
        categories[item["category"]].append(item)
    return {
        "dataset_version": version,
        "total": total,
        "passed": sum(bool(item["passed"]) for item in results),
        "pass_rate": round(sum(bool(item["passed"]) for item in results) / total, 4) if total else 0.0,
        "citation_match_rate": round(
            sum(bool(item["citation_ok"]) for item in citation_cases) / len(citation_cases), 4
        ) if citation_cases else 1.0,
        "safety_guardrail_accuracy": round(
            sum(bool(item["guardrail_ok"]) for item in safety_cases) / len(safety_cases), 4
        ) if safety_cases else 1.0,
        "average_term_coverage": round(
            statistics.fmean(float(item["term_coverage"]) for item in citation_cases), 4
        ) if citation_cases else 1.0,
        "average_confidence": round(statistics.fmean(confidence_values), 4) if confidence_values else 0.0,
        "latency_seconds": {
            "p50": round(percentile(latencies, 0.50), 2),
            "p95": round(percentile(latencies, 0.95), 2),
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
                    "citation_ok", "term_coverage", "latency_seconds", "citation_titles",
                )
                if item.get(key) is not None
            }
            for item in results
            if not item["passed"]
        ],
    }


async def run(
    dataset_path: Path,
    concurrency: int,
    request_interval_seconds: float,
) -> dict[str, Any]:
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = payload["cases"]
    semaphore = asyncio.Semaphore(max(1, concurrency))
    pacer = RequestPacer(request_interval_seconds)
    async with httpx.AsyncClient(timeout=240.0, limits=httpx.Limits(max_connections=max(2, concurrency))) as client:
        token = await get_supabase_token(client)
        results = await asyncio.gather(
            *(run_case(client, token, semaphore, pacer, case) for case in cases)
        )
    return {"summary": summarize(payload["version"], results), "results": results}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--request-interval", type=float, default=7.0)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    report = asyncio.run(run(args.dataset, args.concurrency, args.request_interval))
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
