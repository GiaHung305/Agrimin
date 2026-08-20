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


@pytest.mark.asyncio
async def test_optional_weather_failure_does_not_log_provider_details(
    monkeypatch, caplog
):
    async def failing_geocode(_province):
        raise RuntimeError("weather URL contains sensitive query")

    monkeypatch.setattr(retrieve, "geocode_province_via_mcp", failing_geocode)

    result = await retrieve._retrieve_weather(True, "Đồng Nai")

    assert result is None
    assert "weather URL contains sensitive query" not in caplog.text
    assert caplog.records[-1].error_type == "RuntimeError"


def test_retry_query_is_expanded_and_keeps_original_evidence_scope():
    state = {
        "question": "Câu hỏi gốc",
        "plan": {"need_rag": True},
        "missing_evidence": ["Liều lượng an toàn?"],
        "retry_count": 1,
        "risk_level": "high",
        "context": {},
    }

    queries = retrieve._research_queries(state)

    assert queries == ["Liều lượng an toàn? nhãn và hướng dẫn chính thức Việt Nam"]
    assert state["context"]["research_retry_bases"][queries[0]] == "Liều lượng an toàn?"


def test_first_pass_nutrition_query_adds_balanced_decision_criteria():
    state = {
        "question": "Câu hỏi gốc",
        "plan": {"need_rag": True},
        "research_questions": [
            "Canh tác lúa giảm phát thải nên quản lý dinh dưỡng theo nguyên tắc nào?"
        ],
        "retry_count": 0,
        "context": {},
    }

    queries = retrieve._research_queries(state)

    assert "bón phân cân đối theo nhu cầu cây và phân tích đất" in queries[0]
    assert state["context"]["research_retry_bases"][queries[0]] == (
        state["research_questions"][0]
    )


def test_visual_crop_conflict_anchors_retrieval_to_image_question():
    state = {
        "question": "Sắp thu hoạch được chưa?",
        "plan": {"need_rag": True},
        "research_questions": [
            "Cà chua trồng ngày 21/08/2026 đã thu hoạch được chưa?"
        ],
        "retry_count": 0,
        "context": {
            "plot_seasons": [
                {"crop": "Cà chua", "status": "planned"}
            ]
        },
        "visual_observations": [
            {
                "image_id": "0123456789abcdef",
                "relevance": "agriculture_plant",
                "crop_candidate": "xà lách",
                "plant_part": "whole_plant",
                "confidence": 0.9,
            }
        ],
    }

    queries = retrieve._research_queries(state)

    assert len(queries) == 1
    assert queries[0].startswith("Sắp thu hoạch được chưa?")
    assert "xà lách" in queries[0]
    assert "Cà chua" not in queries[0]
    assert state["research_questions"] == ["Sắp thu hoạch được chưa?"]
    assert state["context"]["visual_crop_context"]["conflict"] is True
