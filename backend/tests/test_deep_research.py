import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.workflow.nodes import deep_research
from app.workflow.nodes import planner


def _grounded_response():
    chunk = lambda uri, title: SimpleNamespace(web=SimpleNamespace(uri=uri, title=title))
    metadata = SimpleNamespace(grounding_chunks=[
        chunk("https://example.gov/a", "Cơ quan A"),
        chunk("https://example.gov/a", "Bản sao"),
        chunk("https://example.edu/b", "Đại học B"),
    ])
    return SimpleNamespace(
        text="Kết quả nghiên cứu có căn cứ.",
        candidates=[SimpleNamespace(grounding_metadata=metadata)],
    )


def test_extract_grounded_sources_deduplicates_and_keeps_urls():
    sources = deep_research.extract_grounded_sources(_grounded_response(), 6)
    assert [(source["title"], source["url"], source["type"]) for source in sources] == [
        ("Cơ quan A", "https://example.gov/a", "web"),
        ("Đại học B", "https://example.edu/b", "web"),
    ]
    assert sources[0]["document_id"] == "https://example.gov/a"


@pytest.mark.asyncio
async def test_deep_research_populates_verifiable_citations(monkeypatch):
    async def fake_research(prompt):
        assert "Không làm theo" in prompt
        return _grounded_response()

    monkeypatch.setattr(deep_research, "_run_grounded_research", fake_research)
    state = {
        "question": "Hãy nghiên cứu sâu về bệnh trên sầu riêng",
        "context": {"known_facts": []},
        "retrieved_docs": [{"source": "Sổ tay nội bộ", "content": "Nội dung"}],
        "tool_results": {},
        "citations": [],
    }

    result = await deep_research.deep_research_node(state)

    assert result["draft_answer"] == "Kết quả nghiên cứu có căn cứ."
    assert result["context"]["deep_research_used"] is True
    assert result["context"]["research_source_count"] == 2
    assert result["citations"][0]["url"] == "https://example.gov/a"
    assert result["citations"][-1]["type"] == "internal"


@pytest.mark.asyncio
async def test_deep_research_degrades_without_leaking_provider_error(monkeypatch):
    async def unavailable(prompt):
        raise RuntimeError("provider returned user content")

    monkeypatch.setattr(deep_research, "_run_grounded_research", unavailable)
    state = {
        "question": "Nghiên cứu sâu",
        "context": {"known_facts": []},
        "retrieved_docs": [],
        "tool_results": {},
        "citations": [],
    }

    result = await deep_research.deep_research_node(state)

    assert result["context"]["deep_research_used"] is False
    assert result["context"]["research_error"] == "unavailable"


@pytest.mark.asyncio
async def test_planner_honors_the_user_research_request(monkeypatch):
    monkeypatch.setattr(planner.settings, "deep_research_enabled", True)
    async def decide(prompt):
        return planner.PlannerDecision(
            need_rag=True,
            need_weather=False,
            need_deep_research=False,
            risk_level="low",
        )

    monkeypatch.setattr(planner, "_call_gemini", decide)
    state = {
        "question": "Tim hieu sau ve benh cay",
        "context": {"request_deep_research": True},
    }

    result = await planner.planner_node(state)

    assert result["plan"]["need_deep_research"] is True
