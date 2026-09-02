from qdrant_client.models import Filter, FieldCondition, MatchValue, QueryRequest

from app.core.qdrant_client import qdrant_client
from app.retrieval.qdrant_setup import COLLECTION_NAME
from app.services.embedding_client import embed_batch, embed_text
from app.retrieval.evidence import is_excluded_source, normalize_evidence


def _normalize_results(results: list, top_k: int) -> list[dict]:
    normalized = [
        normalize_evidence({
            "content": r.payload["content"],
            "title": r.payload.get("title"),
            "source": r.payload.get("source"),
            "source_type": r.payload.get("source_type"),
            "version": r.payload.get("version"),
            "published_date": r.payload.get("published_date"),
            "crop_keys": r.payload.get("crop_keys", []),
            "stages": r.payload.get("stages", []),
            "regions": r.payload.get("regions", []),
            "document_id": r.payload.get("document_id"),
            "chunk_id": r.payload.get("chunk_id") or str(r.id),
            "chunk_index": r.payload.get("chunk_index"),
            "locator": r.payload.get("locator"),
            "is_active": r.payload.get("is_active", True),
            "dense_score": r.score,
        })
        for r in results
    ]
    return [record for record in normalized if not is_excluded_source(record)][:top_k]


def _active_filter() -> Filter:
    return Filter(
        must=[FieldCondition(key="is_active", match=MatchValue(value=True))]
    )


async def dense_search(query: str, top_k: int = 10) -> list[dict]:
    query_vector = await embed_text(query)
    response = await qdrant_client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=max(top_k * 3, top_k),
        query_filter=_active_filter(),
    )
    return _normalize_results(response.points, top_k)


async def dense_search_many(
    queries: list[str], top_k: int = 10
) -> list[list[dict]]:
    """Embed and query independent research questions in two batch calls."""
    if not queries:
        return []
    vectors = await embed_batch(queries)
    if len(vectors) != len(queries):
        raise RuntimeError("embedding service returned an incomplete query batch")
    responses = await qdrant_client.query_batch_points(
        collection_name=COLLECTION_NAME,
        requests=[
            QueryRequest(
                query=vector,
                limit=max(top_k * 3, top_k),
                filter=_active_filter(),
                with_payload=True,
            )
            for vector in vectors
        ],
    )
    if len(responses) != len(queries):
        raise RuntimeError("Qdrant returned an incomplete query batch")
    return [_normalize_results(response.points, top_k) for response in responses]
