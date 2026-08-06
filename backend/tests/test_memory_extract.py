import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.workflow.nodes import memory_extract


class FakeResponse:
    text = '{"has_personal_info": true, "province": "Dak Lak", "crop": "ca phe"}'


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
    monkeypatch.setattr(memory_extract, "_call_gemini", lambda prompt: FakeResponse())
    db = FakeSession()
    state = {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "question": "Toi trong ca phe o Dak Lak",
        "confidence": 0.63,
    }

    await memory_extract.memory_extract_node(state, db)

    assert db.committed
    assert len(db.added) == 1
    assert db.added[0].confidence == 0.63
