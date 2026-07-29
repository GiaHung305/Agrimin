from rank_bm25 import BM25Okapi
from qdrant_client.models import Filter, FieldCondition, MatchValue

from app.core.qdrant_client import qdrant_client
from app.retrieval.qdrant_setup import COLLECTION_NAME


async def bm25_search(query: str, top_k: int = 10) -> list[dict]:
    all_points, _ = await qdrant_client.scroll(
        collection_name=COLLECTION_NAME,
        limit=10000,
        with_payload=True,
        scroll_filter=Filter(
            must=[FieldCondition(key="is_active", match=MatchValue(value=True))]
        ),
    )
    if not all_points:
        return []

    corpus = [p.payload["content"] for p in all_points]
    tokenized_corpus = [doc.lower().split() for doc in corpus]
    bm25 = BM25Okapi(tokenized_corpus)

    tokenized_query = query.lower().split()
    scores = bm25.get_scores(tokenized_query)

    ranked = sorted(zip(all_points, scores), key=lambda x: x[1], reverse=True)[:top_k]

    return [
        {
            "content": p.payload["content"],
            "title": p.payload.get("title"),
            "source": p.payload.get("source"),
            "version": p.payload.get("version"),
            "document_id": p.payload.get("document_id"),
            "bm25_score": float(score),
        }
        for p, score in ranked
        if score > 0
    ]