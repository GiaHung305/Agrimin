import asyncio
import time

from rank_bm25 import BM25Okapi
from qdrant_client.models import Filter, FieldCondition, MatchValue

from app.core.config import settings
from app.core.qdrant_client import qdrant_client
from app.retrieval.qdrant_setup import COLLECTION_NAME

_bm25_index: BM25Okapi | None = None
_indexed_points: list = []
_index_expires_at = 0.0
_index_generation = 0
_index_lock = asyncio.Lock()


def invalidate_bm25_index() -> None:
    """Discard the local index after a document write or deactivation."""
    global _bm25_index, _indexed_points, _index_expires_at, _index_generation
    _bm25_index = None
    _indexed_points = []
    _index_expires_at = 0.0
    _index_generation += 1


async def _get_bm25_index() -> tuple[BM25Okapi | None, list]:
    global _bm25_index, _indexed_points, _index_expires_at
    if _bm25_index is not None and time.monotonic() < _index_expires_at:
        return _bm25_index, _indexed_points

    async with _index_lock:
        # A request may have built the index while this request waited.
        if _bm25_index is not None and time.monotonic() < _index_expires_at:
            return _bm25_index, _indexed_points

        # An ingest/deactivation can happen while Qdrant is being read. In
        # that case rebuild from the new generation instead of publishing a
        # stale local index for the full TTL.
        while True:
            generation = _index_generation
            all_points, _ = await qdrant_client.scroll(
                collection_name=COLLECTION_NAME,
                limit=10000,
                with_payload=True,
                scroll_filter=Filter(
                    must=[FieldCondition(key="is_active", match=MatchValue(value=True))]
                ),
            )
            if generation == _index_generation:
                break
        if not all_points:
            invalidate_bm25_index()
            return None, []

        _indexed_points = all_points
        _bm25_index = BM25Okapi(
            [point.payload["content"].lower().split() for point in all_points]
        )
        _index_expires_at = time.monotonic() + settings.bm25_index_ttl_seconds
        return _bm25_index, _indexed_points


async def bm25_search(query: str, top_k: int = 10) -> list[dict]:
    bm25, all_points = await _get_bm25_index()
    if bm25 is None:
        return []

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
