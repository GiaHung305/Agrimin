from qdrant_client.models import Filter, FieldCondition, MatchValue

from app.core.qdrant_client import qdrant_client
from app.retrieval.qdrant_setup import COLLECTION_NAME
from app.services.embedding_client import embed_text


async def dense_search(query: str, top_k: int = 10) -> list[dict]:
    query_vector = await embed_text(query)

    response = await qdrant_client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=top_k,
        query_filter=Filter(
            must=[FieldCondition(key="is_active", match=MatchValue(value=True))]
        ),
    )
    results = response.points

    return [
        {
            "content": r.payload["content"],
            "title": r.payload.get("title"),
            "source": r.payload.get("source"),
            "version": r.payload.get("version"),
            "document_id": r.payload.get("document_id"),
            "dense_score": r.score,
        }
        for r in results
    ]