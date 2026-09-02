from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.retrieval import bm25_search, dense_search
from app.services import reranker_client


def _point(point_id: str, content: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=point_id,
        score=0.9,
        payload={
            "document_id": f"doc-{point_id}",
            "chunk_id": point_id,
            "content": content,
            "is_active": True,
        },
    )


@pytest.mark.asyncio
async def test_dense_search_many_uses_one_embedding_and_qdrant_batch(monkeypatch):
    embed = AsyncMock(return_value=[[0.1, 0.2], [0.3, 0.4]])
    qdrant = SimpleNamespace(
        query_batch_points=AsyncMock(return_value=[
            SimpleNamespace(points=[_point("chunk-1", "banana")]),
            SimpleNamespace(points=[_point("chunk-2", "pineapple")]),
        ])
    )
    monkeypatch.setattr(dense_search, "embed_batch", embed)
    monkeypatch.setattr(dense_search, "qdrant_client", qdrant)

    result = await dense_search.dense_search_many(["chuối", "dứa"], top_k=3)

    embed.assert_awaited_once_with(["chuối", "dứa"])
    qdrant.query_batch_points.assert_awaited_once()
    assert len(qdrant.query_batch_points.await_args.kwargs["requests"]) == 2
    assert result[0][0]["document_id"] == "doc-chunk-1"
    assert result[1][0]["document_id"] == "doc-chunk-2"


@pytest.mark.asyncio
async def test_bm25_search_many_reuses_one_loaded_index(monkeypatch):
    class FakeBM25:
        def get_scores(self, tokens):
            return [2.0, 0.0] if "chuoi" in tokens else [0.0, 3.0]

    points = [_point("chunk-1", "banana"), _point("chunk-2", "pineapple")]
    load_index = AsyncMock(return_value=(FakeBM25(), points))
    monkeypatch.setattr(bm25_search, "_get_bm25_index", load_index)

    result = await bm25_search.bm25_search_many(["chuối", "dứa"], top_k=2)

    load_index.assert_awaited_once()
    assert result[0][0]["document_id"] == "doc-chunk-1"
    assert result[1][0]["document_id"] == "doc-chunk-2"


@pytest.mark.asyncio
async def test_rerank_many_preserves_scores_per_query(monkeypatch):
    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {
            "scores": [[0.9, 0.2], [0.8]],
            "model": reranker_client.settings.reranker_model,
        },
    )
    client = SimpleNamespace(post=AsyncMock(return_value=response))
    monkeypatch.setattr(reranker_client, "get_ai_service_client", lambda: client)

    result = await reranker_client.rerank_many([
        ("query-1", ["doc-1", "doc-2"]),
        ("query-2", ["doc-3"]),
    ])

    assert result == [[0.9, 0.2], [0.8]]
    payload = client.post.await_args.kwargs["json"]
    assert payload["expected_model"] == reranker_client.settings.reranker_model
    assert payload["items"][0]["query"] == "query-1"
    assert payload["items"][1]["documents"] == ["doc-3"]


@pytest.mark.asyncio
async def test_rerank_many_rejects_response_from_unexpected_model(monkeypatch):
    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"scores": [[0.9]], "model": "unexpected-reranker"},
    )
    client = SimpleNamespace(post=AsyncMock(return_value=response))
    monkeypatch.setattr(reranker_client, "get_ai_service_client", lambda: client)

    with pytest.raises(RuntimeError, match="does not match runtime settings"):
        await reranker_client.rerank_many([("query", ["document"])])
