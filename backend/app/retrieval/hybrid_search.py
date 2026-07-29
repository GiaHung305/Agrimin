from app.retrieval.dense_search import dense_search
from app.retrieval.bm25_search import bm25_search
from app.retrieval.fusion import reciprocal_rank_fusion
from app.services.reranker_client import rerank


async def hybrid_search(query: str, top_k: int = 5) -> list[dict]:
    dense_results = await dense_search(query, top_k=10)
    bm25_results = await bm25_search(query, top_k=10)

    fused = reciprocal_rank_fusion(dense_results, bm25_results)
    if not fused:
        return []

    candidates = fused[:15]
    documents_text = [c["content"] for c in candidates]

    scores = await rerank(query, documents_text)
    reranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)

    return [{**doc, "rerank_score": float(score)} for doc, score in reranked[:top_k]]