import asyncio

from app.core.config import settings
from app.retrieval.dense_search import dense_search
from app.retrieval.bm25_search import bm25_search
from app.retrieval.fusion import reciprocal_rank_fusion
from app.services.reranker_client import rerank


async def hybrid_search(query: str, top_k: int = 5) -> list[dict]:
    dense_results, bm25_results = await asyncio.gather(
        dense_search(query, top_k=10),
        bm25_search(query, top_k=10),
    )

    fused = reciprocal_rank_fusion(
        dense_results,
        bm25_results,
        dense_weight=settings.rrf_dense_weight,
        bm25_weight=settings.rrf_sparse_weight,
    )
    if not fused:
        return []

    candidates = fused[:15]
    documents_text = [c["content"] for c in candidates]

    scores = await rerank(query, documents_text)
    scored = list(zip(candidates, scores))
    if scores and max(scores) >= settings.rerank_min_confidence:
        ranked = sorted(scored, key=lambda item: item[1], reverse=True)
        strategy = "rerank"
    else:
        # Very low cross-encoder probabilities are not strong enough to
        # override dense+sparse consensus. Preserve RRF order while retaining
        # raw reranker scores for guardrail/confidence decisions.
        ranked = scored
        strategy = "fusion_low_rerank_confidence"

    return [
        {**doc, "rerank_score": float(score), "ranking_strategy": strategy}
        for doc, score in ranked[:top_k]
    ]
