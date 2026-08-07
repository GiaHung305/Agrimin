import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.retrieval import bm25_search as bm25_module


class FakeQdrant:
    def __init__(self):
        self.calls = 0

    async def scroll(self, **kwargs):
        self.calls += 1
        return [
            SimpleNamespace(payload={"content": "tuoi nuoc cho sau rieng", "source": "A"}),
            SimpleNamespace(payload={"content": "bon phan ca phe", "source": "B"}),
            SimpleNamespace(payload={"content": "phong tru sau benh", "source": "C"}),
            SimpleNamespace(payload={"content": "lam dat truoc khi trong", "source": "D"}),
        ], None


@pytest.mark.asyncio
async def test_bm25_reuses_index_until_invalidated(monkeypatch):
    fake_qdrant = FakeQdrant()
    monkeypatch.setattr(bm25_module, "qdrant_client", fake_qdrant)
    bm25_module.invalidate_bm25_index()

    first = await bm25_module.bm25_search("tuoi nuoc")
    second = await bm25_module.bm25_search("bon phan")

    assert first[0]["source"] == "A"
    assert second[0]["source"] == "B"
    assert fake_qdrant.calls == 1

    bm25_module.invalidate_bm25_index()
    await bm25_module.bm25_search("tuoi nuoc")
    assert fake_qdrant.calls == 2


@pytest.mark.asyncio
async def test_bm25_excludes_configured_placeholder_sources(monkeypatch):
    class QdrantWithPlaceholder:
        async def scroll(self, **kwargs):
            return [
                SimpleNamespace(payload={"content": "sau rieng", "source": "Test"}),
                SimpleNamespace(payload={"content": "sau rieng", "source": "Khuyen nong"}),
            ], None

    monkeypatch.setattr(bm25_module, "qdrant_client", QdrantWithPlaceholder())
    bm25_module.invalidate_bm25_index()
    result = await bm25_module.bm25_search("sầu riêng")
    assert [item["source"] for item in result] == ["Khuyen nong"]
