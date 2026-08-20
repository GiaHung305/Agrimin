"""Evaluate the local hybrid retriever without invoking a generation model."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import settings
from app.retrieval.hybrid_search import hybrid_search


DEFAULT_DATASET = Path(__file__).with_name("agriculture_benchmark_v2.json")
DEFAULT_BASELINE = Path(__file__).with_name(
    "retrieval_baseline_agriculture_v1.json"
)


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def is_relevant(result: dict[str, Any], relevant_sources: list[str]) -> bool:
    expected = {
        _normalized(source) for source in relevant_sources if _normalized(source)
    }
    candidates = {
        _normalized(result.get("source")),
        _normalized(result.get("title")),
        _normalized(result.get("document_id")),
    }
    return any(
        expected_source in candidate or candidate in expected_source
        for expected_source in expected
        for candidate in candidates
        if candidate
    )


def retrieval_metrics(relevance: list[bool]) -> dict[str, float]:
    first_rank = next((rank for rank, hit in enumerate(relevance, 1) if hit), None)
    dcg = sum(hit / math.log2(rank + 1) for rank, hit in enumerate(relevance, 1))
    relevant_count = sum(relevance)
    ideal_dcg = sum(
        1 / math.log2(rank + 1)
        for rank in range(1, min(relevant_count, len(relevance)) + 1)
    )
    return {
        "recall_at_1": 1.0 if relevance[:1] == [True] else 0.0,
        "recall_at_k": 1.0 if first_rank is not None else 0.0,
        "mrr": 1.0 / first_rank if first_rank is not None else 0.0,
        "ndcg_at_k": dcg / ideal_dcg if ideal_dcg else 0.0,
    }


def evaluate_promotion_gate(
    aggregate: dict[str, float], thresholds: dict[str, float]
) -> dict[str, Any]:
    checks = {
        "recall_at_1": aggregate["recall_at_1"]
        >= thresholds.get("minimum_recall_at_1", 0.0),
        "recall_at_k": aggregate["recall_at_k"]
        >= thresholds["minimum_recall_at_k"],
        "mrr": aggregate["mrr"] >= thresholds["minimum_mrr"],
        "ndcg_at_k": aggregate["ndcg_at_k"]
        >= thresholds["minimum_ndcg_at_k"],
        "mean_latency_ms": aggregate["mean_latency_ms"]
        <= thresholds["maximum_mean_latency_ms"],
    }
    return {"passed": all(checks.values()), "checks": checks}


async def evaluate(dataset_path: Path, top_k: int) -> dict[str, Any]:
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    item_results = []
    items = dataset.get("items") or dataset.get("cases") or []
    for item in items:
        relevant_sources = (
            item.get("relevant_sources")
            or item.get("expected_citations_any")
            or []
        )
        if item.get("category") == "safety" or not relevant_sources:
            continue
        query = item.get("query") or item.get("question")
        if not query:
            continue
        started = time.perf_counter()
        results = await hybrid_search(query, top_k=top_k)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        relevance = [is_relevant(result, relevant_sources) for result in results]
        metrics = retrieval_metrics(relevance)
        item_results.append(
            {
                "id": item.get("id"),
                "query": query,
                "category": item["category"],
                "relevant_sources": relevant_sources,
                "latency_ms": latency_ms,
                **metrics,
                "ranked_evidence": [
                    {
                        "document_id": result.get("document_id"),
                        "chunk_id": result.get("chunk_id"),
                        "title": result.get("title"),
                        "source": result.get("source"),
                        "published_date": result.get("published_date"),
                        "ranking_strategy": result.get("ranking_strategy"),
                        "fusion_score": result.get("fusion_score"),
                        "rerank_score": result.get("rerank_score"),
                        "relevant": relevance[index],
                    }
                    for index, result in enumerate(results)
                ],
            }
        )

    count = len(item_results)
    aggregate = {
        metric: sum(item[metric] for item in item_results) / count if count else 0.0
        for metric in ("recall_at_1", "recall_at_k", "mrr", "ndcg_at_k")
    }
    aggregate["mean_latency_ms"] = (
        sum(item["latency_ms"] for item in item_results) / count if count else 0.0
    )
    return {
        "dataset_version": dataset["version"],
        "knowledge_base_version": settings.knowledge_base_version,
        "top_k": top_k,
        "aggregate": aggregate,
        "items": item_results,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()
    result = await evaluate(args.dataset, args.top_k)
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    result["gate"] = evaluate_promotion_gate(
        result["aggregate"], baseline["promotion_thresholds"]
    )
    if args.output:
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    printable = (
        {
            "dataset_version": result["dataset_version"],
            "knowledge_base_version": result["knowledge_base_version"],
            "top_k": result["top_k"],
            "aggregate": result["aggregate"],
            "gate": result["gate"],
        }
        if args.summary_only
        else result
    )
    print(json.dumps(printable, ensure_ascii=False, indent=2))
    if not result["gate"]["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
