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
async def test_hybrid_search_degrades_to_sparse_when_dense_is_unavailable(
    monkeypatch,
):
    async def unavailable_dense(*args, **kwargs):
        raise ConnectionError("temporary qdrant read failure")

    sparse = [{"document_id": "sparse", "chunk_id": "1", "content": "safe"}]
    monkeypatch.setattr(hybrid_module, "dense_search", unavailable_dense)
    monkeypatch.setattr(
        hybrid_module,
        "bm25_search",
        lambda *args, **kwargs: asyncio.sleep(0, result=sparse),
    )
    monkeypatch.setattr(
        hybrid_module,
        "rerank",
        lambda *args: asyncio.sleep(0, result=[0.9]),
    )

    result = await hybrid_module.hybrid_search("query")

    assert result[0]["document_id"] == "sparse"


@pytest.mark.asyncio
async def test_hybrid_search_preserves_fusion_when_reranker_is_unavailable(
    monkeypatch,
):
    evidence = [{"document_id": "doc", "chunk_id": "1", "content": "safe"}]
    monkeypatch.setattr(
        hybrid_module,
        "dense_search",
        lambda *args, **kwargs: asyncio.sleep(0, result=evidence),
    )
    monkeypatch.setattr(
        hybrid_module,
        "bm25_search",
        lambda *args, **kwargs: asyncio.sleep(0, result=[]),
    )

    async def unavailable_reranker(*args, **kwargs):
        raise TimeoutError("temporary reranker timeout")

    monkeypatch.setattr(hybrid_module, "rerank", unavailable_reranker)

    result = await hybrid_module.hybrid_search("query")

    assert result[0]["document_id"] == "doc"
    assert result[0]["rerank_score"] == 0.0
    assert result[0]["ranking_strategy"] == "fusion_rerank_unavailable"


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


@pytest.mark.asyncio
async def test_hybrid_search_many_batches_ml_calls_and_keeps_query_results(
    monkeypatch,
):
    queries = ["Chuối Tây Nguyên ra hoa", "Dứa bị thối nõn"]
    dense_groups = [
        [{
            "document_id": "banana",
            "chunk_id": "1",
            "content": "chuối ra hoa",
            "crop_keys": ["banana"],
        }],
        [{
            "document_id": "pineapple",
            "chunk_id": "2",
            "content": "dứa thối nõn",
            "crop_keys": ["pineapple"],
        }],
    ]
    calls = {"dense": 0, "sparse": 0, "rerank": 0}

    async def dense_many(received, top_k):
        calls["dense"] += 1
        assert received == queries
        return dense_groups

    async def sparse_many(received, top_k):
        calls["sparse"] += 1
        assert received == queries
        return [[], []]

    async def batch_rerank(items):
        calls["rerank"] += 1
        assert [query for query, _ in items] == queries
        return [[0.91], [0.92]]

    monkeypatch.setattr(hybrid_module, "dense_search_many", dense_many)
    monkeypatch.setattr(hybrid_module, "bm25_search_many", sparse_many)
    monkeypatch.setattr(hybrid_module, "rerank_many", batch_rerank)

    results = await hybrid_module.hybrid_search_many(queries)

    assert calls == {"dense": 1, "sparse": 1, "rerank": 1}
    assert results[0][0]["document_id"] == "banana"
    assert results[0][0]["rerank_score"] == pytest.approx(0.91)
    assert results[1][0]["document_id"] == "pineapple"
    assert results[1][0]["rerank_score"] == pytest.approx(0.92)


@pytest.mark.asyncio
async def test_hybrid_search_many_degrades_when_batch_reranker_is_unavailable(
    monkeypatch,
):
    evidence = [{"document_id": "doc", "chunk_id": "1", "content": "safe"}]
    monkeypatch.setattr(
        hybrid_module,
        "dense_search_many",
        lambda *args, **kwargs: asyncio.sleep(0, result=[evidence]),
    )
    monkeypatch.setattr(
        hybrid_module,
        "bm25_search_many",
        lambda *args, **kwargs: asyncio.sleep(0, result=[[]]),
    )

    async def unavailable(*args, **kwargs):
        raise TimeoutError("reranker unavailable")

    monkeypatch.setattr(hybrid_module, "rerank_many", unavailable)

    result = await hybrid_module.hybrid_search_many(["query"])

    assert result[0][0]["document_id"] == "doc"
    assert result[0][0]["ranking_strategy"] == "fusion_rerank_unavailable"


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

    assert [item["document_id"] for item in selected] == [
        "fusion", "dense", "sparse",
    ]
    assert len(selected) == hybrid_module.MAX_RERANK_CANDIDATES


def test_rerank_candidates_prioritize_explicit_crop_scope_within_budget():
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
    assert len(selected) == hybrid_module.MAX_RERANK_CANDIDATES


def test_crop_intent_distinguishes_positive_crop_from_negated_crop():
    positive, negative = hybrid_module._query_crop_intent(
        "Mùi tây parsley Petroselinum crispum, không phải rau mùi coriander"
    )

    assert "parsley" in positive
    assert "coriander" in negative
    assert "coriander" not in positive


def test_visual_crop_filter_removes_documents_for_other_named_crops():
    documents = [
        {"document_id": "lettuce", "title": "Xà lách - nhận biết độ thu hoạch"},
        {"document_id": "artichoke", "title": "Quy trình thu hoạch atisô"},
        {"document_id": "chili", "title": "Ớt - độ chín khi thu hoạch"},
        {"document_id": "watercress", "title": "Xà lách xoong - cách thu hái"},
        {"document_id": "generic", "title": "Nguyên tắc thu hoạch rau ăn lá"},
    ]

    filtered = hybrid_module.filter_conflicting_crop_evidence(
        "Sắp thu hoạch chưa? Quan sát thị giác: xà lách", documents
    )

    assert [item["document_id"] for item in filtered] == ["lettuce", "generic"]


def test_longer_crop_name_does_not_also_match_shorter_crop_name():
    assert hybrid_module.crop_keys_for_text("xà lách xoong") == {"watercress"}


def test_common_production_phrase_is_not_misread_as_cassava():
    assert hybrid_module.crop_keys_for_text(
        "Sản xuất rau an toàn và bón phân cân đối"
    ) == set()


@pytest.mark.parametrize(
    ("question", "unexpected_crop"),
    [
        ("Tôi muốn hỏi cách tưới", "garlic"),
        ("Hãy đưa ra phương án phù hợp", "pineapple"),
        ("Hệ thống tưới đang hoạt động", "chives"),
        ("Tôi muốn nghe tư vấn", "turmeric"),
        ("Giải pháp riêng cho vườn", "galangal"),
    ],
)
def test_common_accented_words_are_not_misread_as_crop_names(
    question,
    unexpected_crop,
):
    assert unexpected_crop not in hybrid_module.crop_keys_for_text(question)


@pytest.mark.parametrize(
    ("question", "expected_crop"),
    [
        ("Tỏi bị vàng lá", "garlic"),
        ("Dứa bị thối nõn", "pineapple"),
        ("Hẹ cần bón gì", "chives"),
        ("Nghệ bị thối củ", "turmeric"),
        ("Riềng nên thu hoạch lúc nào", "galangal"),
        ("Sắn cần đất thế nào", "cassava"),
    ],
)
def test_ambiguous_crop_names_still_match_when_accents_are_explicit(
    question,
    expected_crop,
):
    assert expected_crop in hybrid_module.crop_keys_for_text(question)


def test_reviewed_crop_scope_overrides_ambiguous_generic_title():
    documents = [
        {
            "document_id": "wrong",
            "title": "Hướng dẫn tưới và dinh dưỡng",
            "crop_keys": ["mango"],
        },
        {
            "document_id": "right",
            "title": "Hướng dẫn tưới và dinh dưỡng",
            "crop_keys": ["banana"],
        },
        {
            "document_id": "generic",
            "title": "Nguyên tắc tưới cây ăn quả",
            "crop_keys": [],
        },
    ]

    filtered = hybrid_module.filter_conflicting_crop_evidence(
        "Tưới chuối thế nào?",
        documents,
    )

    assert [item["document_id"] for item in filtered] == ["right", "generic"]


@pytest.mark.asyncio
async def test_explicit_crop_query_removes_disjoint_reviewed_scope(monkeypatch):
    wrong = {
        "document_id": "mango",
        "chunk_id": "1",
        "title": "Hướng dẫn tưới cây ăn quả",
        "crop_keys": ["mango"],
        "content": "tưới nhỏ giọt",
    }
    right = {
        "document_id": "banana",
        "chunk_id": "2",
        "title": "Hướng dẫn tưới cây ăn quả",
        "crop_keys": ["banana"],
        "content": "tưới nhỏ giọt",
    }
    results = [wrong, right]
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
        lambda *args: asyncio.sleep(0, result=[0.99, 0.90]),
    )

    ranked = await hybrid_module.hybrid_search("Vườn chuối nên tưới thế nào?")

    assert [item["document_id"] for item in ranked] == ["banana"]


@pytest.mark.asyncio
async def test_visual_hybrid_search_does_not_return_other_crop_titles(monkeypatch):
    results = [
        {
            "document_id": "artichoke", "chunk_id": "1",
            "title": "Quy trình thu hoạch atisô", "content": "atisô",
        },
        {
            "document_id": "lettuce", "chunk_id": "2",
            "title": "Xà lách - nhận biết độ thu hoạch", "content": "xà lách",
        },
        {
            "document_id": "chili", "chunk_id": "3",
            "title": "Ớt - độ chín khi thu hoạch", "content": "ớt",
        },
    ]
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
        lambda *args: asyncio.sleep(0, result=[0.98, 0.90, 0.95]),
    )

    ranked = await hybrid_module.hybrid_search(
        "Sắp thu hoạch chưa? Quan sát thị giác: xà lách"
    )

    assert [item["document_id"] for item in ranked] == ["lettuce"]


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


def test_stage_region_intent_prefers_matching_reviewed_scope():
    ranked = [
        ({
            "title": "Chuối tưới giai đoạn cây con",
            "stages": ["initial"],
            "regions": ["northern_mountains"],
        }, 0.97),
        ({
            "title": "Chuối tưới giai đoạn ra hoa",
            "stages": ["mid_season"],
            "regions": ["central_highlands"],
        }, 0.94),
        ({
            "title": "Nguyên tắc tưới chuối toàn quốc",
            "stages": ["all"],
            "regions": ["national"],
        }, 0.93),
    ]

    result, applied = hybrid_module._apply_stage_region_intent(
        "Chuối ở Tây Nguyên đang ra hoa thì tưới thế nào?",
        ranked,
    )

    assert applied is True
    assert result[0][0]["regions"] == ["central_highlands"]
    assert result[1][0]["regions"] == ["national"]


def test_stage_region_intent_does_not_override_much_stronger_semantic_match():
    ranked = [
        ({"title": "Tưới chuối", "regions": ["national"]}, 0.98),
        ({"title": "Bệnh cây khác", "regions": ["central_highlands"]}, 0.40),
    ]

    result, applied = hybrid_module._apply_stage_region_intent(
        "Chuối ở Tây Nguyên nên tưới thế nào?",
        ranked,
    )

    assert applied is False
    assert result[0][1] == pytest.approx(0.98)


def test_scope_intent_recognizes_only_explicit_stage_and_macro_region():
    assert hybrid_module._scope_intent(
        "Cà phê Tây Nguyên đang ra hoa"
    ) == ({"mid_season"}, {"central_highlands"})
    assert hybrid_module._scope_intent(
        "Cây đang phát triển tốt ở Lâm Đồng"
    ) == (set(), set())
    assert hybrid_module._scope_intent(
        "Lúa đang làm đòng ở đồng bằng sông Hồng"
    ) == ({"mid_season"}, {"red_river_delta"})


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
