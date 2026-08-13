import asyncio
import re
import unicodedata

from app.core.config import settings
from app.retrieval.dense_search import dense_search
from app.retrieval.bm25_search import bm25_search
from app.retrieval.evidence import evidence_identity
from app.retrieval.fusion import reciprocal_rank_fusion
from app.services.farm_monitoring import VEGETABLE_POLICY_SPECS
from app.services.reranker_client import rerank


MAX_RERANK_CANDIDATES = 3
MAX_RERANK_CHARACTERS = 800
MAX_BM25_CANDIDATES = 50
NEGATED_CROP_WINDOW_TOKENS = 4
MAX_INTENT_RERANK_SCORE_GAP = 0.15


def _normalize_crop_text(value: str) -> str:
    normalized = "".join(
        character
        for character in unicodedata.normalize("NFD", value.casefold())
        if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", normalized).split())


_CROP_ALIASES = {
    crop_key: {
        _normalize_crop_text(crop_key.replace("_", " ")),
        _normalize_crop_text(label),
        *(_normalize_crop_text(alias) for alias in aliases),
    }
    for crop_key, (label, _, aliases) in VEGETABLE_POLICY_SPECS.items()
}

_TOPIC_ALIASES = {
    "establishment": {
        "thoi vu", "gieo", "cay con", "giong", "chuan bi dat",
    },
    "nutrition": {
        "dinh duong", "phan bon", "bon lot", "bon thuc", "lich bon",
    },
    "water_pollination": {
        "do am", "tuoi", "thuy phan", "mat do",
    },
    "pest_ipm": {
        "sau benh", "ipm", "luan canh", "ve sinh", "che phu",
    },
    "harvest": {
        "thu hoach", "thu hai", "cat cuong",
    },
}


def _phrase_positions(tokens: list[str], phrase: str) -> list[int]:
    phrase_tokens = phrase.split()
    if not phrase_tokens:
        return []
    width = len(phrase_tokens)
    return [
        index
        for index in range(len(tokens) - width + 1)
        if tokens[index : index + width] == phrase_tokens
    ]


def _is_negated_crop(tokens: list[str], crop_position: int) -> bool:
    search_start = max(0, crop_position - NEGATED_CROP_WINDOW_TOKENS - 2)
    for index in range(search_start, crop_position):
        marker_width = 0
        if tokens[index : index + 2] in (["khong", "phai"], ["khong", "la"]):
            marker_width = 2
        if marker_width and 0 <= crop_position - index - marker_width <= NEGATED_CROP_WINDOW_TOKENS:
            return True
    return False


def _query_crop_intent(query: str) -> tuple[set[str], set[str]]:
    tokens = _normalize_crop_text(query).split()
    positive: set[str] = set()
    negative: set[str] = set()
    for crop_key, aliases in _CROP_ALIASES.items():
        positions = {
            position
            for alias in aliases
            for position in _phrase_positions(tokens, alias)
        }
        if not positions:
            continue
        if any(not _is_negated_crop(tokens, position) for position in positions):
            positive.add(crop_key)
        if any(_is_negated_crop(tokens, position) for position in positions):
            negative.add(crop_key)
    return positive, negative - positive


def _title_crop_keys(title: str) -> set[str]:
    padded_title = f" {_normalize_crop_text(title)} "
    return {
        crop_key
        for crop_key, aliases in _CROP_ALIASES.items()
        if any(f" {alias} " in padded_title for alias in aliases if alias)
    }


def _topic_keys(value: str) -> set[str]:
    padded = f" {_normalize_crop_text(value)} "
    return {
        topic
        for topic, aliases in _TOPIC_ALIASES.items()
        if any(f" {alias} " in padded for alias in aliases)
    }


def _apply_explicit_crop_intent(
    query: str,
    ranked: list[tuple[dict, float]],
) -> tuple[list[tuple[dict, float]], bool]:
    """Honor explicit crop exclusions after semantic reranking.

    Cross-encoders can treat a phrase such as ``không phải rau mùi`` as strong
    positive evidence for coriander. Only reorder when the query also names a
    positive crop and a distinct negated crop, and only from crop names present
    in evidence titles. This keeps the correction bounded and auditable.
    """
    positive, negative = _query_crop_intent(query)
    if not positive or not negative:
        return ranked, False

    best_score = max((float(score) for _, score in ranked), default=0.0)

    def intent_tier(item: tuple[dict, float]) -> int:
        if float(item[1]) < best_score - MAX_INTENT_RERANK_SCORE_GAP:
            return -1
        title_keys = _title_crop_keys(str(item[0].get("title") or ""))
        if title_keys & positive:
            return 2
        if title_keys & negative:
            return 0
        return 1

    reordered = sorted(
        enumerate(ranked),
        key=lambda indexed: (-intent_tier(indexed[1]), indexed[0]),
    )
    result = [item for _, item in reordered]
    return result, result != ranked


def _apply_title_topic_intent(
    query: str,
    ranked: list[tuple[dict, float]],
) -> tuple[list[tuple[dict, float]], bool]:
    """Prefer the requested subtopic among documents for the named crop.

    A cross-encoder can correctly identify a crop yet rank a neighboring slice
    (for example moisture above nutrition). Reordering is deliberately bounded
    to titles that name a positive crop from the query and an audited topic cue;
    raw semantic scores remain available in the response.
    """
    positive_crops, _ = _query_crop_intent(query)
    query_topics = _topic_keys(query)
    if not positive_crops or not query_topics:
        return ranked, False

    best_score = max((float(score) for _, score in ranked), default=0.0)

    def topic_matches(item: tuple[dict, float]) -> int:
        if float(item[1]) < best_score - MAX_INTENT_RERANK_SCORE_GAP:
            return -1
        title = str(item[0].get("title") or "")
        if not (_title_crop_keys(title) & positive_crops):
            return 0
        return len(_topic_keys(title) & query_topics)

    if not any(topic_matches(item) for item in ranked):
        return ranked, False
    reordered = sorted(
        enumerate(ranked),
        key=lambda indexed: (-topic_matches(indexed[1]), indexed[0]),
    )
    result = [item for _, item in reordered]
    return result, result != ranked


def _select_rerank_candidates(
    fused: list[dict],
    dense_results: list[dict],
    bm25_results: list[dict],
    query: str = "",
) -> list[dict]:
    """Keep CPU work bounded without dropping either retriever's leader."""
    fused_by_identity = {evidence_identity(item): item for item in fused}
    positive_crops, _ = _query_crop_intent(query)
    crop_title_candidates = [
        item
        for item in fused
        if _title_crop_keys(str(item.get("title") or "")) & positive_crops
    ]
    leaders = [
        *(fused[:1]),
        *crop_title_candidates,
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
        bm25_search(query, top_k=MAX_BM25_CANDIDATES),
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
    candidates = _select_rerank_candidates(
        fused, dense_results, bm25_results, query=query
    )
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

    ranked, crop_intent_applied = _apply_explicit_crop_intent(query, ranked)
    if crop_intent_applied:
        strategy = f"{strategy}_crop_intent"
    ranked, topic_intent_applied = _apply_title_topic_intent(query, ranked)
    if topic_intent_applied:
        strategy = f"{strategy}_topic_intent"

    return [
        {**doc, "rerank_score": float(score), "ranking_strategy": strategy}
        for doc, score in ranked[:top_k]
    ]
