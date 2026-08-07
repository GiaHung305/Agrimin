import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio

import pytest

from app.retrieval import hybrid_search as hybrid_module


@pytest.mark.asyncio
async def test_hybrid_search_runs_dense_and_bm25_concurrently(monkeypatch):
    started = []
    release = asyncio.Event()
    both_started = asyncio.Event()

    async def dense(*args, **kwargs):
        started.append("dense")
        if len(started) == 2:
            both_started.set()
        await release.wait()
        return [{"content": "dense document"}]

    async def bm25(*args, **kwargs):
        started.append("bm25")
        if len(started) == 2:
            both_started.set()
        await release.wait()
        return [{"content": "bm25 document"}]

    monkeypatch.setattr(hybrid_module, "dense_search", dense)
    monkeypatch.setattr(hybrid_module, "bm25_search", bm25)
    monkeypatch.setattr(hybrid_module, "rerank", lambda *args: asyncio.sleep(0, result=[0.9, 0.8]))
    task = asyncio.create_task(hybrid_module.hybrid_search("query"))
    await asyncio.wait_for(both_started.wait(), timeout=0.1)
    assert set(started) == {"dense", "bm25"}
    release.set()
    await task


@pytest.mark.asyncio
async def test_low_confidence_reranker_does_not_override_fusion(monkeypatch):
    monkeypatch.setattr(
        hybrid_module,
        "dense_search",
        lambda *args, **kwargs: asyncio.sleep(
            0,
            result=[
                {"document_id": "right", "chunk_id": "1", "content": "right"},
                {"document_id": "wrong", "chunk_id": "2", "content": "wrong"},
            ],
        ),
    )
    monkeypatch.setattr(
        hybrid_module,
        "bm25_search",
        lambda *args, **kwargs: asyncio.sleep(
            0,
            result=[{"document_id": "right", "chunk_id": "1", "content": "right"}],
        ),
    )
    monkeypatch.setattr(
        hybrid_module,
        "rerank",
        lambda *args: asyncio.sleep(0, result=[0.05, 0.075]),
    )
    result = await hybrid_module.hybrid_search("query")
    assert result[0]["document_id"] == "right"
    assert result[0]["ranking_strategy"] == "fusion_low_rerank_confidence"
