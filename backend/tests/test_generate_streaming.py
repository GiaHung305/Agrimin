import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.workflow.nodes import generate


async def fake_stream(*args, **kwargs):
    yield SimpleNamespace(text="Xin ")
    yield SimpleNamespace(text="chao")


@pytest.mark.asyncio
async def test_generate_node_writes_tokens_for_low_risk_answer(monkeypatch):
    events = []
    monkeypatch.setattr(generate, "get_stream_writer", lambda: events.append)
    monkeypatch.setattr(generate, "stream_content", fake_stream)
    state = {
        "risk_level": "low",
        "retrieved_docs": [],
        "context": {},
        "tool_results": {},
        "question": "Xin chao",
    }

    result = await generate.generate_node(state)

    assert result["draft_answer"] == "Xin chao"
    assert events == [
        {"type": "token", "text": "Xin "},
        {"type": "token", "text": "chao"},
    ]


@pytest.mark.asyncio
async def test_generate_node_buffers_high_risk_answer(monkeypatch):
    events = []
    monkeypatch.setattr(generate, "get_stream_writer", lambda: events.append)
    monkeypatch.setattr(generate, "stream_content", fake_stream)
    state = {
        "risk_level": "high",
        "retrieved_docs": [],
        "context": {},
        "tool_results": {},
        "question": "Xin chao",
    }

    result = await generate.generate_node(state)

    assert result["draft_answer"] == "Xin chao"
    assert events == []


@pytest.mark.asyncio
async def test_generate_node_emits_traceable_citation_metadata(monkeypatch):
    monkeypatch.setattr(generate, "get_stream_writer", lambda: lambda event: None)
    monkeypatch.setattr(generate, "stream_content", fake_stream)
    state = {
        "risk_level": "low",
        "retrieved_docs": [{
            "document_id": "doc-1",
            "chunk_id": "chunk-2",
            "chunk_index": 2,
            "title": "Khuyến nông",
            "source": "https://example.test/doc",
            "version": "2026-08",
            "locator": "https://example.test/doc#page=3",
            "is_active": True,
            "content": "Nội dung",
            "fusion_score": 0.03,
            "rerank_score": 0.91,
        }],
        "context": {},
        "tool_results": {},
        "question": "Hỏi",
    }
    result = await generate.generate_node(state)
    citation = result["citations"][0]
    assert citation["document_id"] == "doc-1"
    assert citation["chunk_id"] == "chunk-2"
    assert citation["version"] == "2026-08"
    assert citation["rerank_score"] == 0.91
    assert citation["citation_id"] == "E1"
