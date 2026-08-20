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


@pytest.mark.asyncio
async def test_bm25_uses_reviewed_title_for_crop_identity(monkeypatch):
    class QdrantWithCropTitles:
        async def scroll(self, **kwargs):
            return [
                SimpleNamespace(
                    payload={
                        "title": "Kỹ thuật trồng rau mồng tơi an toàn",
                        "content": "Thời vụ, làm đất và chăm sóc chi tiết.",
                        "source": "Khuyen nong mong toi",
                    }
                ),
                SimpleNamespace(
                    payload={
                        "title": "Kỹ thuật trồng rau khác",
                        "content": "Cách trồng và chăm sóc rau an toàn.",
                        "source": "Khuyen nong rau khac",
                    }
                ),
            ], None

    monkeypatch.setattr(bm25_module, "qdrant_client", QdrantWithCropTitles())
    bm25_module.invalidate_bm25_index()

    result = await bm25_module.bm25_search("trồng rau mồng tơi an toàn")

    assert result[0]["source"] == "Khuyen nong mong toi"


@pytest.mark.asyncio
async def test_bm25_indexes_every_qdrant_scroll_page(monkeypatch):
    class PaginatedQdrant:
        def __init__(self):
            self.offsets = []

        async def scroll(self, **kwargs):
            offset = kwargs.get("offset")
            self.offsets.append(offset)
            if offset is None:
                return [
                    SimpleNamespace(
                        payload={"content": "tai lieu cu", "source": "A"}
                    )
                ], "page-2"
            return [
                SimpleNamespace(
                    payload={
                        "content": "giu nuoc tiet kiem nuoc bang che phu",
                        "source": "CGIAR",
                    }
                )
            ], None

    fake_qdrant = PaginatedQdrant()
    monkeypatch.setattr(bm25_module, "qdrant_client", fake_qdrant)
    bm25_module.invalidate_bm25_index()

    result = await bm25_module.bm25_search("giu nuoc tiet kiem nuoc")

    assert fake_qdrant.offsets == [None, "page-2"]
    assert result[0]["source"] == "CGIAR"
