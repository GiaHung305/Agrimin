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


DEFAULT_DATASET = Path(__file__).with_name("retrieval_dataset_v2.json")
DEFAULT_BASELINE = Path(__file__).with_name("retrieval_baseline_v2.json")


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def is_relevant(result: dict[str, Any], relevant_sources: list[str]) -> bool:
    expected = {_normalized(source) for source in relevant_sources}
    candidates = {
        _normalized(result.get("source")),
        _normalized(result.get("title")),
        _normalized(result.get("document_id")),
    }
    return bool(expected & candidates)


def retrieval_metrics(relevance: list[bool]) -> dict[str, float]:
    first_rank = next((rank for rank, hit in enumerate(relevance, 1) if hit), None)
    dcg = sum(hit / math.log2(rank + 1) for rank, hit in enumerate(relevance, 1))
    relevant_count = sum(relevance)
    ideal_dcg = sum(
        1 / math.log2(rank + 1)
        for rank in range(1, min(relevant_count, len(relevance)) + 1)
    )
    return {
        "recall_at_k": 1.0 if first_rank is not None else 0.0,
        "mrr": 1.0 / first_rank if first_rank is not None else 0.0,
        "ndcg_at_k": dcg / ideal_dcg if ideal_dcg else 0.0,
    }


def evaluate_promotion_gate(
    aggregate: dict[str, float], thresholds: dict[str, float]
) -> dict[str, Any]:
    checks = {
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
    for item in dataset["items"]:
        started = time.perf_counter()
        results = await hybrid_search(item["query"], top_k=top_k)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        relevance = [is_relevant(result, item["relevant_sources"]) for result in results]
        metrics = retrieval_metrics(relevance)
        item_results.append(
            {
                "query": item["query"],
                "category": item["category"],
                "latency_ms": latency_ms,
                **metrics,
                "ranked_evidence": [
                    {
                        "document_id": result.get("document_id"),
                        "chunk_id": result.get("chunk_id"),
                        "source": result.get("source"),
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
        for metric in ("recall_at_k", "mrr", "ndcg_at_k")
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
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    result = await evaluate(args.dataset, args.top_k)
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    result["gate"] = evaluate_promotion_gate(
        result["aggregate"], baseline["promotion_thresholds"]
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["gate"]["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
