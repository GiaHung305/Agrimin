from collections.abc import Sequence


RELEVANT_DOCUMENT_THRESHOLD = 0.65


def compute_confidence(
    rerank_scores: Sequence[float],
    reflection_notes: str | None,
    retry_count: int = 0,
    weather_requested: bool = False,
    weather_available: bool = False,
) -> float:
    """Estimate answer confidence from observable evidence signals.

    ``rerank_scores`` is a list of calibrated relevance probabilities returned
    by the embedding service.  The result is an estimate, not a model-provided
    probability; its weights must later be calibrated against the golden set.
    """
    scores = [min(1.0, max(0.0, float(score))) for score in rerank_scores]
    if not scores:
        return 0.0

    top_relevance = max(scores)
    corroborating_sources = sum(
        score >= RELEVANT_DOCUMENT_THRESHOLD for score in scores
    )
    corroboration = min(corroborating_sources / 3, 1.0)

    # 45%: strongest retrieved evidence; 20%: independent supporting chunks.
    confidence = 0.45 * top_relevance + 0.20 * corroboration

    # Reflection evaluates whether the generated answer is actually grounded.
    if reflection_notes == "sufficient":
        confidence += 0.25
    elif reflection_notes == "need_more_search":
        confidence -= 0.20

    # Repeated retrieval means the original evidence was insufficient.
    confidence -= 0.08 * min(max(retry_count, 0), 2)

    # Do not overstate an answer that required, but could not obtain, weather.
    if weather_requested and not weather_available:
        confidence -= 0.10

    return round(max(0.0, min(1.0, confidence)), 2)
