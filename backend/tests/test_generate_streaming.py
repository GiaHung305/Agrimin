import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.workflow.nodes import generate


class FakeModels:
    async def generate_content_stream(self, **kwargs):
        async def chunks():
            yield SimpleNamespace(text="Xin ")
            yield SimpleNamespace(text="chao")

        return chunks()


class FakeClient:
    aio = SimpleNamespace(models=FakeModels())


@pytest.mark.asyncio
async def test_generate_node_writes_tokens_for_low_risk_answer(monkeypatch):
    events = []
    monkeypatch.setattr(generate, "get_stream_writer", lambda: events.append)
    monkeypatch.setattr(generate, "client", FakeClient())
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
    monkeypatch.setattr(generate, "client", FakeClient())
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
