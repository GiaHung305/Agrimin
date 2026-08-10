import asyncio

from app.core.config import settings
from app.retrieval.dense_search import dense_search
from app.retrieval.bm25_search import bm25_search
from app.retrieval.evidence import evidence_identity
from app.retrieval.fusion import reciprocal_rank_fusion
from app.services.reranker_client import rerank


MAX_RERANK_CANDIDATES = 3
MAX_RERANK_CHARACTERS = 800


def _select_rerank_candidates(
    fused: list[dict],
    dense_results: list[dict],
    bm25_results: list[dict],
) -> list[dict]:
    """Keep CPU work bounded without dropping either retriever's leader."""
    fused_by_identity = {evidence_identity(item): item for item in fused}
    leaders = [
        *(fused[:1]),
        *(dense_results[:1]),
        *(bm25_results[:1]),
        *fused,
    ]
    selected: list[dict] = []
    seen: set[str] = set()
    for item in leaders:
        identity = evidence_identity(item)
        if identity in seen:
            continue
        seen.add(identity)
        selected.append(fused_by_identity.get(identity, item))
        if len(selected) == MAX_RERANK_CANDIDATES:
            break
    return selected


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

    # The cross-encoder intentionally runs on CPU on the target 4 GB RTX 3050
    # setup. Bound each parallel research query so cold-start batches do not
    # queue beyond the backend's AI-service timeout.
    candidates = _select_rerank_candidates(fused, dense_results, bm25_results)
    # The cross-encoder only needs a bounded relevance preview. Keep the full
    # chunk in ``candidates`` for generation and citation traceability.
    documents_text = [c["content"][:MAX_RERANK_CHARACTERS] for c in candidates]

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
