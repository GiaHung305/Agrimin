from collections.abc import Mapping, Sequence


RELEVANT_DOCUMENT_THRESHOLD = 0.65
TRUSTED_ANSWER_CONFIDENCE_THRESHOLD = 0.70
GROUNDED_WEB_MAX_CONTRIBUTION = 0.30


def compute_confidence(
    rerank_scores: Sequence[float],
    reflection_notes: str | None,
    retry_count: int = 0,
    weather_requested: bool = False,
    weather_available: bool = False,
    research_source_count: int = 0,
    visual_confidences: Sequence[float] = (),
    trusted_context_count: int = 0,
    independent_document_count: int | None = None,
) -> float:
    """Estimate answer confidence from observable evidence signals.

    ``rerank_scores`` is a list of calibrated relevance probabilities returned
    by the embedding service.  The result is an estimate, not a model-provided
    probability; its weights must later be calibrated against the golden set.
    """
    scores = [min(1.0, max(0.0, float(score))) for score in rerank_scores]
    visual_scores = [
        min(1.0, max(0.0, float(score))) for score in visual_confidences
    ]
    trusted_records = max(int(trusted_context_count), 0)
    if (
        not scores
        and research_source_count <= 0
        and not visual_scores
        and trusted_records <= 0
    ):
        return 0.0

    top_relevance = max(scores, default=0.0)
    relevant_chunks = sum(
        score >= RELEVANT_DOCUMENT_THRESHOLD for score in scores
    )
    corroborating_documents = relevant_chunks
    if independent_document_count is not None:
        corroborating_documents = min(
            relevant_chunks,
            max(int(independent_document_count), 0),
        )
    corroboration = min(corroborating_documents / 3, 1.0)

    # 45%: strongest evidence; 20%: independently identified documents.
    confidence = 0.45 * top_relevance + 0.20 * corroboration

    # Provider grounding proves attribution, not independent entailment or
    # source authority. Even three independent web domains plus a positive
    # reflection therefore stay below the trusted-answer threshold unless
    # internal evidence or another trusted signal corroborates the answer.
    confidence += GROUNDED_WEB_MAX_CONTRIBUTION * min(
        max(research_source_count, 0) / 3,
        1.0,
    )

    # User-owned farm/season records are authoritative for direct facts such as
    # crop, growth stage and saved dates. They support those facts only when the
    # typed planner says the answer uses farm context; callers pass zero for
    # unrelated questions.
    confidence += 0.65 * min(trusted_records, 1)

    # Typed vision observations can support an objective description, but not
    # a diagnosis. Keep their contribution below the standalone certainty bar.
    if visual_scores and not scores and research_source_count <= 0:
        confidence += 0.60 * max(visual_scores)

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


def compute_weather_risk_confidence(
    *, available_signals: int, total_signals: int, threshold_margin: float
) -> float:
    """Estimate deterministic weather-risk confidence from input quality.

    This is confidence in the policy evaluation, not the probability that a
    disease is present. It therefore rewards complete weather inputs and a
    clear distance from the notification threshold.
    """
    if total_signals <= 0 or available_signals <= 0:
        return 0.0
    completeness = min(max(available_signals / total_signals, 0.0), 1.0)
    margin = min(max(float(threshold_margin), 0.0), 1.0)
    confidence = 0.40 + 0.40 * completeness + 0.20 * margin
    if available_signals < 2:
        confidence -= 0.15
    return round(max(0.0, min(1.0, confidence)), 2)


def compute_weather_response_confidence(
    forecast: Sequence[Mapping[str, object]], *, from_cache: bool = False
) -> float:
    """Estimate fidelity of a deterministic forecast response.

    This score describes how completely AgriMind can reproduce the validated
    provider payload; it is not the probability that the forecast event will
    occur. Temperature, humidity and description are optional in the weather
    contract, while rain probability and amount are required. Longer horizons
    and cached payloads receive small penalties so a forecast is never presented
    as absolute certainty.
    """
    days = [item for item in forecast if isinstance(item, Mapping)]
    if not days:
        return 0.0

    available_signals = 0
    total_signals = 5 * len(days)
    for item in days:
        available_signals += int(item.get("rain_probability") is not None)
        available_signals += int(item.get("rain_mm") is not None)
        available_signals += int(any(
            item.get(field) is not None
            for field in ("temp", "temp_min", "temp_max")
        ))
        available_signals += int(any(
            item.get(field) is not None
            for field in ("humidity", "humidity_max")
        ))
        available_signals += int(bool(str(item.get("description") or "").strip()))

    completeness = available_signals / total_signals
    horizon_penalty = 0.02 * min(len(days) - 1, 2)
    cache_penalty = 0.02 if from_cache else 0.0
    confidence = 0.70 + 0.22 * completeness - horizon_penalty - cache_penalty
    return round(max(0.0, min(0.92, confidence)), 2)
