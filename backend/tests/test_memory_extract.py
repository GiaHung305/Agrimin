import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.workflow.nodes import memory_extract


class FakeSession:
    def __init__(self):
        self.added = []
        self.committed = False

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_memory_fact_uses_graph_confidence(monkeypatch):
    async def extract(prompt):
        return memory_extract.MemoryExtraction(
            has_personal_info=True, province="Dak Lak", crop="ca phe"
        )

    monkeypatch.setattr(memory_extract, "_call_gemini", extract)
    db = FakeSession()
    state = {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "question": "Toi trong ca phe o Dak Lak",
        "confidence": 0.63,
        "guardrail_status": "pass",
    }

    await memory_extract.memory_extract_node(state, db)

    assert db.committed
    assert len(db.added) == 1
    assert db.added[0].confidence == 0.63


@pytest.mark.asyncio
async def test_memory_extraction_skips_blocked_answer(monkeypatch):
    async def should_not_run(prompt):
        raise AssertionError("extractor must not run for blocked answers")

    monkeypatch.setattr(memory_extract, "_call_gemini", should_not_run)
    db = FakeSession()
    state = {"guardrail_status": "block", "question": "unsafe"}
    await memory_extract.memory_extract_node(state, db)
    assert not db.added
    assert not db.committed
