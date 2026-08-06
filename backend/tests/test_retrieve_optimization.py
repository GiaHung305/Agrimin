import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.workflow.nodes import retrieve


@pytest.mark.asyncio
async def test_retrieve_skips_rag_when_planner_does_not_need_it(monkeypatch):
    async def unexpected_search(*args, **kwargs):
        raise AssertionError("RAG should not run")

    monkeypatch.setattr(retrieve, "hybrid_search", unexpected_search)
    state = {
        "question": "Xin chao",
        "plan": {"need_rag": False, "need_weather": False},
        "context": {},
    }

    result = await retrieve.retrieve_node(state)

    assert result["retrieved_docs"] == []
    assert result["context"]["rerank_scores"] == []
    assert result["tool_results"] == {}


@pytest.mark.asyncio
async def test_retrieve_runs_rag_and_weather_concurrently(monkeypatch):
    started = []
    both_started = asyncio.Event()
    release = asyncio.Event()

    async def search(*args, **kwargs):
        started.append("rag")
        if len(started) == 2:
            both_started.set()
        await release.wait()
        return [{"content": "doc", "source": "source", "rerank_score": 0.8}]

    async def geocode(province):
        started.append("weather")
        if len(started) == 2:
            both_started.set()
        await release.wait()
        return 10.0, 106.0

    async def weather(*args):
        return {"forecast": "sunny"}

    monkeypatch.setattr(retrieve, "hybrid_search", search)
    monkeypatch.setattr(retrieve, "geocode_province_via_mcp", geocode)
    monkeypatch.setattr(retrieve, "get_weather_via_mcp", weather)
    state = {
        "question": "Thoi tiet hom nay?",
        "plan": {"need_rag": True, "need_weather": True},
        "context": {"province": "Dong Nai"},
    }

    task = asyncio.create_task(retrieve.retrieve_node(state))
    await asyncio.wait_for(both_started.wait(), timeout=0.1)
    release.set()
    result = await task

    assert result["tool_results"]["weather"]["forecast"] == "sunny"
