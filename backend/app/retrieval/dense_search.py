from qdrant_client.models import Filter, FieldCondition, MatchValue

from app.core.qdrant_client import qdrant_client
from app.retrieval.qdrant_setup import COLLECTION_NAME
from app.services.embedding_client import embed_text
from app.retrieval.evidence import is_excluded_source, normalize_evidence


async def dense_search(query: str, top_k: int = 10) -> list[dict]:
    query_vector = await embed_text(query)

    response = await qdrant_client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=max(top_k * 3, top_k),
        query_filter=Filter(
            must=[FieldCondition(key="is_active", match=MatchValue(value=True))]
        ),
    )
    results = response.points

    normalized = [
        normalize_evidence({
            "content": r.payload["content"],
            "title": r.payload.get("title"),
            "source": r.payload.get("source"),
            "source_type": r.payload.get("source_type"),
            "version": r.payload.get("version"),
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
