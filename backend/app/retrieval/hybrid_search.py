import asyncio
import logging
import re
import unicodedata

from app.core.config import settings
from app.retrieval.dense_search import dense_search, dense_search_many
from app.retrieval.bm25_search import bm25_search, bm25_search_many
from app.retrieval.evidence import evidence_identity
from app.retrieval.fusion import reciprocal_rank_fusion
from app.services.farm_monitoring import POLICIES, VEGETABLE_POLICY_SPECS
from app.services.reranker_client import rerank, rerank_many

logger = logging.getLogger(__name__)

MAX_RERANK_CANDIDATES = settings.rerank_max_candidates
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
        _normalize_crop_text(policy.crop_label),
        *(
            _normalize_crop_text(alias)
            for alias in VEGETABLE_POLICY_SPECS.get(
                crop_key, ("", "", ())
            )[2]
        ),
    }
    for crop_key, policy in POLICIES.items()
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

_STAGE_ALIASES = {
    "initial": {
        "cay con", "moi trong", "moi gieo", "gieo hat", "xuong giong",
        "nay mam", "uom cay",
    },
    "development": {
        "sinh truong", "phat trien than la", "hoi xanh",
        "kien thiet co ban",
    },
    "mid_season": {
        "ra hoa", "dau qua", "dau trai", "nuoi qua", "nuoi trai",
        "tro bong",
    },
    "late_season": {
        "chin", "thu hoach", "sau thu hoach", "cuoi vu",
    },
}

_REGION_ALIASES = {
    "northern_mountains": {
        "trung du mien nui phia bac", "mien nui phia bac", "vung dong bac",
        "vung tay bac",
    },
    "red_river_delta": {
        "dong bang song hong", "dong bang bac bo",
    },
    "north_central_coast": {
        "bac trung bo", "bac trung bo va duyen hai mien trung",
    },
    "south_central_coast": {
        "nam trung bo", "duyen hai nam trung bo",
    },
    "central_highlands": {"tay nguyen"},
    "southeast": {"dong nam bo"},
    "mekong_delta": {
        "dong bang song cuu long", "dbscl", "mien tay nam bo",
        "mien tay",
    },
}

_GENERAL_SCOPE_VALUES = {"all", "national"}

# These Vietnamese crop names collide with very common words after accent
# folding. Require the original accented token before using them as a hard
# evidence-scope boundary. Unaccented ambiguous input remains searchable, but
# does not filter out otherwise relevant evidence.
_ACCENT_REQUIRED_SINGLE_CROP_FORMS = {
    ("cassava", "san"): {"sắn"},
    ("pineapple", "dua"): {"dứa"},
    ("garlic", "toi"): {"tỏi"},
    ("chives", "he"): {"hẹ"},
    ("lemongrass", "sa"): {"sả"},
    ("turmeric", "nghe"): {"nghệ"},
    ("galangal", "rieng"): {"riềng"},
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


def _maximal_crop_phrase_matches(
    tokens: list[str],
) -> list[tuple[str, int, int]]:
    """Prefer the longest crop alias when crop names overlap."""
    matches = [
        (crop_key, position, len(alias.split()))
        for crop_key, aliases in _CROP_ALIASES.items()
        for alias in aliases
        for position in _phrase_positions(tokens, alias)
    ]
    maximal = [
        match
        for match in matches
        if not any(
            other_key != match[0]
            and other_width > match[2]
            and other_start <= match[1]
            and match[1] + match[2] <= other_start + other_width
            for other_key, other_start, other_width in matches
        )
    ]
    # Accent folding makes the crop ``sắn`` and the common word ``sản``
    # identical. Do not treat phrases such as ``sản xuất`` as cassava intent.
    return [
        match
        for match in maximal
        if not (
            match[0] == "cassava"
            and match[2] == 1
            and tokens[match[1] : match[1] + 2] == ["san", "xuat"]
        )
    ]


def _crop_phrase_matches(value: str) -> list[tuple[str, int, int]]:
    normalized_tokens = _normalize_crop_text(value).split()
    original_tokens = re.findall(
        r"[^\W_]+|\d+",
        unicodedata.normalize("NFC", value.casefold()),
        flags=re.UNICODE,
    )
    matches = _maximal_crop_phrase_matches(normalized_tokens)
    return [
        match
        for match in matches
        if (
            match[2] != 1
            or (match[0], normalized_tokens[match[1]])
            not in _ACCENT_REQUIRED_SINGLE_CROP_FORMS
            or (
                match[1] < len(original_tokens)
                and original_tokens[match[1]]
                in _ACCENT_REQUIRED_SINGLE_CROP_FORMS[
                    (match[0], normalized_tokens[match[1]])
                ]
            )
        )
    ]


def _query_crop_intent(query: str) -> tuple[set[str], set[str]]:
    tokens = _normalize_crop_text(query).split()
    positive: set[str] = set()
    negative: set[str] = set()
    matches = _crop_phrase_matches(query)
    for crop_key in _CROP_ALIASES:
        positions = {position for key, position, _ in matches if key == crop_key}
        if not positions:
            continue
        if any(not _is_negated_crop(tokens, position) for position in positions):
            positive.add(crop_key)
        if any(_is_negated_crop(tokens, position) for position in positions):
            negative.add(crop_key)
    return positive, negative - positive


def _title_crop_keys(title: str) -> set[str]:
    return {crop_key for crop_key, _, _ in _crop_phrase_matches(title)}


def _document_crop_keys(document: dict) -> set[str]:
    """Prefer reviewed scope metadata while retaining a legacy title fallback."""
    structured = {
        str(crop_key).strip()
        for crop_key in (document.get("crop_keys") or [])
        if str(crop_key).strip()
    }
    return structured or _title_crop_keys(str(document.get("title") or ""))


def crop_keys_for_text(value: str) -> set[str]:
    """Return positive canonical crop keys explicitly named in text."""
    positive, _ = _query_crop_intent(value)
    return positive


def filter_conflicting_crop_evidence(
    query: str, documents: list
) -> list:
    """Drop evidence whose title explicitly names a different crop.

    Generic multi-crop documents remain eligible. This strict filter is used
    for image-grounded queries so a visually identified lettuce cannot cite a
    document specifically about artichoke, chili, or another crop.
    """
    query_crops = crop_keys_for_text(query)
    if not query_crops:
        return documents
    filtered = []
    for item in documents:
        document = item[0] if isinstance(item, tuple) else item
        document_crops = _document_crop_keys(document)
        if not document_crops or document_crops & query_crops:
            filtered.append(item)
    return filtered


def _topic_keys(value: str) -> set[str]:
    padded = f" {_normalize_crop_text(value)} "
    return {
        topic
        for topic, aliases in _TOPIC_ALIASES.items()
        if any(f" {alias} " in padded for alias in aliases)
    }


def _alias_keys(value: str, aliases_by_key: dict[str, set[str]]) -> set[str]:
    padded = f" {_normalize_crop_text(value)} "
    return {
        key
        for key, aliases in aliases_by_key.items()
        if any(f" {alias} " in padded for alias in aliases)
    }


def _scope_intent(query: str) -> tuple[set[str], set[str]]:
    stages = _alias_keys(query, _STAGE_ALIASES)
    # Accent folding makes the rice stage ``làm đòng`` collide with the
    # province ``Lâm Đồng``. Only accept the original agricultural phrase.
    if re.search(r"\blàm\s+đòng\b", unicodedata.normalize("NFC", query.casefold())):
        stages.add("mid_season")
    return stages, _alias_keys(query, _REGION_ALIASES)


def _scope_match_score(document: dict, query: str) -> int:
    requested_stages, requested_regions = _scope_intent(query)
    score = 0
    for field, requested in (
        ("stages", requested_stages),
        ("regions", requested_regions),
    ):
        if not requested:
            continue
        document_scope = {
            str(value).strip()
            for value in (document.get(field) or [])
            if str(value).strip()
        }
        specific_scope = document_scope - _GENERAL_SCOPE_VALUES
        if not specific_scope:
            continue
        score += 1 if specific_scope & requested else -1
    return score


def _apply_stage_region_intent(
    query: str,
    ranked: list[tuple[dict, float]],
) -> tuple[list[tuple[dict, float]], bool]:
    """Prefer reviewed stage/region scope without creating a hard filter."""
    if not any(_scope_intent(query)):
        return ranked, False
    best_score = max((float(score) for _, score in ranked), default=0.0)

    def ranking_score(item: tuple[dict, float]) -> int:
        if float(item[1]) < best_score - MAX_INTENT_RERANK_SCORE_GAP:
            return -100
        return _scope_match_score(item[0], query)

    if not any(ranking_score(item) > 0 for item in ranked):
        return ranked, False
    reordered = sorted(
        enumerate(ranked),
        key=lambda indexed: (-ranking_score(indexed[1]), indexed[0]),
    )
    result = [item for _, item in reordered]
    return result, result != ranked


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
        title_keys = _document_crop_keys(item[0])
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
        if not (_document_crop_keys(item[0]) & positive_crops):
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
        if _document_crop_keys(item) & positive_crops
    ]
    scoped_crop_candidates = [
        item
        for item in fused
        if _scope_match_score(item, query) > 0
        and (
            not positive_crops
            or _document_crop_keys(item) & positive_crops
        )
    ]
    leaders = [
        *(fused[:1]),
        *scoped_crop_candidates,
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


def _retrieval_or_empty(result: object, *, kind: str) -> list[dict]:
    if isinstance(result, Exception):
        logger.warning(
            "%s retrieval unavailable; continuing with the other retriever "
            "dependency_error=%s",
            kind,
            type(result).__name__,
        )
        return []
    return list(result)  # type: ignore[arg-type]


def _prepare_rerank_candidates(
    query: str,
    dense_results: list[dict],
    bm25_results: list[dict],
) -> list[dict]:
    fused = reciprocal_rank_fusion(
        dense_results,
        bm25_results,
        dense_weight=settings.rrf_dense_weight,
        bm25_weight=settings.rrf_sparse_weight,
    )
    if not fused:
        return []
    return _select_rerank_candidates(
        fused, dense_results, bm25_results, query=query
    )


def _finalize_ranking(
    query: str,
    candidates: list[dict],
    scores: list[float],
    *,
    reranker_unavailable: bool,
    top_k: int,
) -> list[dict]:
    if not candidates:
        return []

    scored = list(zip(candidates, scores))
    if scores and max(scores) >= settings.rerank_min_confidence:
        ranked = sorted(scored, key=lambda item: item[1], reverse=True)
        strategy = "rerank"
    else:
        # Very low cross-encoder probabilities are not strong enough to
        # override dense+sparse consensus. Preserve RRF order while retaining
        # raw reranker scores for guardrail/confidence decisions.
        ranked = scored
        strategy = (
            "fusion_rerank_unavailable"
            if reranker_unavailable
            else "fusion_low_rerank_confidence"
        )

    ranked, crop_intent_applied = _apply_explicit_crop_intent(query, ranked)
    if crop_intent_applied:
        strategy = f"{strategy}_crop_intent"
    ranked, topic_intent_applied = _apply_title_topic_intent(query, ranked)
    if topic_intent_applied:
        strategy = f"{strategy}_topic_intent"
    ranked, scope_intent_applied = _apply_stage_region_intent(query, ranked)
    if scope_intent_applied:
        strategy = f"{strategy}_scope_intent"

    # An explicit crop name is a hard scope boundary. Keep generic multi-crop
    # guidance, but never return evidence reviewed for a disjoint crop.
    ranked = filter_conflicting_crop_evidence(query, ranked)

    return [
        {**doc, "rerank_score": float(score), "ranking_strategy": strategy}
        for doc, score in ranked[:top_k]
    ]


async def hybrid_search(query: str, top_k: int = 5) -> list[dict]:
    dense_result, bm25_result = await asyncio.gather(
        dense_search(query, top_k=10),
        bm25_search(query, top_k=MAX_BM25_CANDIDATES),
        return_exceptions=True,
    )
    dense_results = _retrieval_or_empty(dense_result, kind="Dense")
    bm25_results = _retrieval_or_empty(bm25_result, kind="Sparse")
    candidates = _prepare_rerank_candidates(
        query, dense_results, bm25_results
    )
    if not candidates:
        return []
    documents_text = [
        candidate["content"][:MAX_RERANK_CHARACTERS]
        for candidate in candidates
    ]
    reranker_unavailable = False
    try:
        scores = await rerank(query, documents_text)
        if len(scores) != len(candidates):
            raise RuntimeError("reranker returned an incomplete result")
    except Exception:
        reranker_unavailable = True
        logger.warning("Reranker unavailable; preserving fused retrieval order")
        scores = [0.0] * len(candidates)
    return _finalize_ranking(
        query,
        candidates,
        scores,
        reranker_unavailable=reranker_unavailable,
        top_k=top_k,
    )


async def hybrid_search_many(
    queries: list[str], top_k: int = 5
) -> list[list[dict]]:
    """Run independent hybrid searches with batched ML service calls."""
    if not queries:
        return []
    dense_batch, bm25_batch = await asyncio.gather(
        dense_search_many(queries, top_k=10),
        bm25_search_many(queries, top_k=MAX_BM25_CANDIDATES),
        return_exceptions=True,
    )
    if isinstance(dense_batch, Exception):
        logger.warning(
            "Dense batch unavailable; continuing with sparse retrieval "
            "dependency_error=%s",
            type(dense_batch).__name__,
        )
        dense_groups = [[] for _ in queries]
    else:
        dense_groups = dense_batch
    if isinstance(bm25_batch, Exception):
        logger.warning(
            "Sparse batch unavailable; continuing with dense retrieval "
            "dependency_error=%s",
            type(bm25_batch).__name__,
        )
        bm25_groups = [[] for _ in queries]
    else:
        bm25_groups = bm25_batch
    if len(dense_groups) != len(queries) or len(bm25_groups) != len(queries):
        raise RuntimeError("retrieval returned an incomplete research batch")

    candidates_by_query = [
        _prepare_rerank_candidates(query, dense_results, bm25_results)
        for query, dense_results, bm25_results in zip(
            queries, dense_groups, bm25_groups
        )
    ]
    nonempty_indexes = [
        index
        for index, candidates in enumerate(candidates_by_query)
        if candidates
    ]
    scores_by_query: list[list[float]] = [
        [] for _ in queries
    ]
    reranker_unavailable = False
    if nonempty_indexes:
        try:
            grouped_scores = await rerank_many([
                (
                    queries[index],
                    [
                        candidate["content"][:MAX_RERANK_CHARACTERS]
                        for candidate in candidates_by_query[index]
                    ],
                )
                for index in nonempty_indexes
            ])
            if len(grouped_scores) != len(nonempty_indexes):
                raise RuntimeError("reranker returned an incomplete batch")
            for index, scores in zip(nonempty_indexes, grouped_scores):
                if len(scores) != len(candidates_by_query[index]):
                    raise RuntimeError("reranker returned incomplete item scores")
                scores_by_query[index] = scores
        except Exception:
            reranker_unavailable = True
            logger.warning(
                "Batch reranker unavailable; preserving fused retrieval order"
            )
            for index in nonempty_indexes:
                scores_by_query[index] = [
                    0.0 for _ in candidates_by_query[index]
                ]

    return [
        _finalize_ranking(
            query,
            candidates,
            scores,
            reranker_unavailable=reranker_unavailable,
            top_k=top_k,
        )
        for query, candidates, scores in zip(
            queries, candidates_by_query, scores_by_query
        )
    ]
