def reciprocal_rank_fusion(dense_results: list[dict], bm25_results: list[dict], k: int = 60) -> list[dict]:
    scores: dict[str, float] = {}
    content_map: dict[str, dict] = {}

    for rank, doc in enumerate(dense_results):
        key = doc["content"][:100]
        scores[key] = scores.get(key, 0) + 1 / (k + rank + 1)
        content_map[key] = doc

    for rank, doc in enumerate(bm25_results):
        key = doc["content"][:100]
        scores[key] = scores.get(key, 0) + 1 / (k + rank + 1)
        content_map[key] = doc

    ranked_keys = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)
    return [content_map[k] for k in ranked_keys]