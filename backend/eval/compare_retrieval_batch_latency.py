"""Compare legacy concurrent retrieval with the batched research path."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.retrieval.evidence import evidence_identity
from app.retrieval.hybrid_search import (
    MAX_RERANK_CANDIDATES,
    hybrid_search,
    hybrid_search_many,
)


DEFAULT_QUERIES = [
    "Dấu hiệu nhận biết bệnh thối nõn trên cây dứa",
    "Dấu hiệu nhận biết bệnh thối rễ trên cây dứa",
    "Các biện pháp ưu tiên quản lý bệnh thối nõn và thối rễ trên cây dứa",
]


async def _timed(call) -> tuple[list[list[dict]], float]:
    started = time.perf_counter()
    result = await call()
    return result, round((time.perf_counter() - started) * 1000, 1)


def _summary(results: list[list[dict]]) -> list[dict[str, Any]]:
    return [
        {
            "results": len(group),
            "top_identity": evidence_identity(group[0]) if group else None,
            "top_title": group[0].get("title") if group else None,
            "top_rerank_score": (
                round(float(group[0].get("rerank_score") or 0.0), 6)
                if group else 0.0
            ),
        }
        for group in results
    ]


async def compare(queries: list[str]) -> dict[str, Any]:
    # Warm BM25 and model inference before comparing either implementation.
    await hybrid_search_many(queries, top_k=5)
    legacy, legacy_ms = await _timed(
        lambda: asyncio.gather(*(
            hybrid_search(query, top_k=5) for query in queries
        ))
    )
    batched, batched_ms = await _timed(
        lambda: hybrid_search_many(queries, top_k=5)
    )
    legacy_summary = _summary(legacy)
    batched_summary = _summary(batched)
    quality_preserved = all(
        old["top_identity"] == new["top_identity"]
        and old["top_identity"] is not None
        for old, new in zip(legacy_summary, batched_summary)
    )
    return {
        "queries": queries,
        "rerank_max_candidates": MAX_RERANK_CANDIDATES,
        "legacy_concurrent_ms": legacy_ms,
        "batched_ms": batched_ms,
        "latency_reduction_ms": round(legacy_ms - batched_ms, 1),
        "speedup": round(legacy_ms / batched_ms, 3) if batched_ms else None,
        "top_identity_preserved": quality_preserved,
        "legacy": legacy_summary,
        "batched": batched_summary,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", action="append", dest="queries")
    args = parser.parse_args()
    print(json.dumps(
        await compare(args.queries or DEFAULT_QUERIES),
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    asyncio.run(main())
