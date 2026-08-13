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


@pytest.mark.asyncio
async def test_hybrid_search_bounds_cpu_reranker_candidates(monkeypatch):
    dense = [
        {
            "document_id": "dense",
            "chunk_id": str(index),
            "content": f"dense-{index}-" + ("x" * 1000),
        }
        for index in range(10)
    ]
    sparse = [
        {
            "document_id": "sparse",
            "chunk_id": str(index),
            "content": f"sparse-{index}-" + ("x" * 1000),
        }
        for index in range(10)
    ]
    captured = {}

    monkeypatch.setattr(
        hybrid_module,
        "dense_search",
        lambda *args, **kwargs: asyncio.sleep(0, result=dense),
    )
    monkeypatch.setattr(
        hybrid_module,
        "bm25_search",
        lambda *args, **kwargs: asyncio.sleep(0, result=sparse),
    )

    async def rerank(query, documents):
        captured["count"] = len(documents)
        captured["max_characters"] = max(map(len, documents))
        return [0.9] * len(documents)

    monkeypatch.setattr(hybrid_module, "rerank", rerank)

    await hybrid_module.hybrid_search("query")

    assert captured["count"] == hybrid_module.MAX_RERANK_CANDIDATES
    assert captured["max_characters"] == hybrid_module.MAX_RERANK_CHARACTERS


def test_rerank_candidates_include_dense_and_sparse_leaders():
    fused = [
        {"document_id": "fusion", "chunk_id": "1", "content": "fusion"},
        {"document_id": "other", "chunk_id": "2", "content": "other"},
    ]
    dense = [
        {"document_id": "dense", "chunk_id": "3", "content": "dense"},
    ]
    sparse = [
        {"document_id": "sparse", "chunk_id": "4", "content": "sparse"},
    ]

    selected = hybrid_module._select_rerank_candidates(fused, dense, sparse)

    assert [item["document_id"] for item in selected] == ["fusion", "dense", "sparse"]


def test_rerank_candidates_reserve_room_for_explicit_crop_title():
    fusion = {"document_id": "fusion", "chunk_id": "1", "content": "generic"}
    old_crop = {
        "document_id": "old-crop", "chunk_id": "2",
        "title": "Cẩm nang đậu cô ve và đậu đũa", "content": "canh tác",
    }
    harvest = {
        "document_id": "harvest", "chunk_id": "3",
        "title": "Đậu đũa - nhận biết độ non khi thu", "content": "thu quả non",
    }
    dense_leader = {"document_id": "dense", "chunk_id": "4", "content": "dense"}
    fused = [fusion, old_crop, harvest, dense_leader]

    selected = hybrid_module._select_rerank_candidates(
        fused,
        [dense_leader],
        [old_crop, harvest],
        query="Đậu đũa thu lúc quả non thế nào?",
    )

    assert [item["document_id"] for item in selected] == [
        "fusion", "old-crop", "harvest",
    ]


def test_crop_intent_distinguishes_positive_crop_from_negated_crop():
    positive, negative = hybrid_module._query_crop_intent(
        "Mùi tây parsley Petroselinum crispum, không phải rau mùi coriander"
    )

    assert "parsley" in positive
    assert "coriander" in negative
    assert "coriander" not in positive


def test_topic_intent_distinguishes_nutrition_from_moisture_for_same_crop():
    ranked = [
        ({"title": "Bí ngòi miền Bắc - mật độ, độ ẩm và thụ phấn"}, 0.97),
        ({"title": "Bí ngòi miền Bắc - dinh dưỡng và lịch bón"}, 0.95),
    ]

    result, applied = hybrid_module._apply_title_topic_intent(
        "Bí ngòi cần lịch bón lót và bón thúc theo giai đoạn nào?",
        ranked,
    )

    assert applied is True
    assert "dinh dưỡng" in result[0][0]["title"]
    assert result[0][1] == pytest.approx(0.95)


def test_topic_intent_does_not_override_much_stronger_semantic_match():
    ranked = [
        ({"title": "Bảng gieo trồng và thu hoạch cho nhiều cây rau"}, 0.96),
        ({"title": "Cải cầu vồng - gieo trồng và tưới nước"}, 0.50),
    ]

    result, applied = hybrid_module._apply_title_topic_intent(
        "Tìm bảng gieo trồng cho cải cầu vồng chard và rau bina spinach",
        ranked,
    )

    assert applied is False
    assert result[0][1] == pytest.approx(0.96)


def test_crop_intent_does_not_override_much_stronger_semantic_match():
    ranked = [
        ({"title": "Thử nghiệm nhà kính cho sáu loại rau gia vị"}, 0.99),
        ({"title": "Mùi tây parsley - thời vụ và khoảng cách gieo"}, 0.37),
    ]

    result, applied = hybrid_module._apply_explicit_crop_intent(
        "Thử nghiệm nhà kính mùi tây parsley, không phải ngò rí coriander",
        ranked,
    )

    assert applied is False
    assert result[0][1] == pytest.approx(0.99)


@pytest.mark.asyncio
async def test_explicit_crop_exclusion_corrects_cross_encoder_negation(monkeypatch):
    coriander = {
        "document_id": "coriander",
        "chunk_id": "1",
        "title": "Cẩm nang trồng ngò rí an toàn",
        "content": "rau mùi coriander",
    }
    parsley = {
        "document_id": "parsley",
        "chunk_id": "2",
        "title": "Mùi tây parsley - thời vụ và khoảng cách gieo",
        "content": "mùi tây parsley Petroselinum crispum",
    }
    results = [coriander, parsley]
    monkeypatch.setattr(
        hybrid_module,
        "dense_search",
        lambda *args, **kwargs: asyncio.sleep(0, result=results),
    )
    monkeypatch.setattr(
        hybrid_module,
        "bm25_search",
        lambda *args, **kwargs: asyncio.sleep(0, result=results),
    )
    monkeypatch.setattr(
        hybrid_module,
        "rerank",
        lambda *args: asyncio.sleep(0, result=[0.97, 0.93]),
    )

    ranked = await hybrid_module.hybrid_search(
        "Mùi tây parsley, không phải rau mùi coriander"
    )

    assert ranked[0]["document_id"] == "parsley"
    assert ranked[0]["ranking_strategy"] == "rerank_crop_intent"
    assert ranked[0]["rerank_score"] == pytest.approx(0.93)
