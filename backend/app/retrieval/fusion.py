from app.retrieval.evidence import evidence_identity, normalize_evidence


def reciprocal_rank_fusion(
    dense_results: list[dict],
    bm25_results: list[dict],
    k: int = 60,
    dense_weight: float = 1.0,
    bm25_weight: float = 1.0,
) -> list[dict]:
    scores: dict[str, float] = {}
    content_map: dict[str, dict] = {}

    for rank, doc in enumerate(dense_results):
        key = evidence_identity(doc)
        scores[key] = scores.get(key, 0) + dense_weight / (k + rank + 1)
        content_map[key] = {**content_map.get(key, {}), **doc}

    for rank, doc in enumerate(bm25_results):
        key = evidence_identity(doc)
        scores[key] = scores.get(key, 0) + bm25_weight / (k + rank + 1)
        content_map[key] = {**content_map.get(key, {}), **doc}

    ranked_keys = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)
    return [
        normalize_evidence({**content_map[key], "fusion_score": scores[key]})
        for key in ranked_keys
    ]
