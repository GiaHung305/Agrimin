import hashlib
import json
import logging
import re
from datetime import datetime, timezone

from app.core.redis_client import redis_client
from app.core.model_registry import runtime_fingerprint
from app.services.embedding_client import embed_text

CACHE_TTL_SECONDS = 3600
SIMILARITY_THRESHOLD = 0.95
logger = logging.getLogger(__name__)
_REALTIME_PATTERN = re.compile(
    r"\b(hôm nay|hiện tại|bây giờ|thời tiết|mưa|nắng|nhiệt độ|độ ẩm|bão|gió)\b",
    re.IGNORECASE,
)


def is_realtime_sensitive_question(question: str) -> bool:
    return bool(_REALTIME_PATTERN.search(question))


def _context_key(
    user_id: str,
    province: str | None,
    crop: str | None,
    *,
    time_window: str | None = None,
) -> str:
    """Scope cache entries to the user because answers can use private memory."""
    user_hash = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:16]
    province = (province or "unknown").lower().strip()
    crop = (crop or "unknown").lower().strip()
    time_window = time_window or datetime.now(timezone.utc).strftime("%Y%m%d%H")
    return f"{runtime_fingerprint()}:{time_window}:{user_hash}:{province}:{crop}"


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


async def get_cached_answer(
    user_id: str,
    question: str,
    province: str | None,
    crop: str | None,
) -> dict | None:
    """Return a matching answer, treating cache/embedding failures as a miss."""
    try:
        index_key = f"semcache_index:{_context_key(user_id, province, crop)}"
        cached_index_raw = await redis_client.get(index_key)
        if not cached_index_raw:
            return None

        query_vector = await embed_text(question)
        for entry in json.loads(cached_index_raw):
            similarity = _cosine_similarity(query_vector, entry["vector"])
            if similarity >= SIMILARITY_THRESHOLD:
                answer_raw = await redis_client.get(entry["answer_key"])
                if answer_raw:
                    result = json.loads(answer_raw)
                    result["from_cache"] = True
                    return result
        return None
    except Exception:
        logger.warning("Semantic cache lookup failed; treating it as a cache miss", exc_info=True)
        return None


async def store_answer(
    user_id: str,
    question: str,
    province: str | None,
    crop: str | None,
    answer_data: dict,
):
    """Store an answer opportunistically without failing the chat response."""
    try:
        context_key = _context_key(user_id, province, crop)
        index_key = f"semcache_index:{context_key}"
        query_vector = await embed_text(question)
        question_hash = hashlib.sha256(question.encode("utf-8")).hexdigest()[:16]

        answer_key = f"semcache_answer:{context_key}:{question_hash}"
        await redis_client.set(
            answer_key,
            json.dumps(answer_data, ensure_ascii=False),
            ex=CACHE_TTL_SECONDS,
        )

        cached_index_raw = await redis_client.get(index_key)
        cached_index = json.loads(cached_index_raw) if cached_index_raw else []
        cached_index.append({"answer_key": answer_key, "vector": query_vector})
        await redis_client.set(index_key, json.dumps(cached_index[-50:]), ex=CACHE_TTL_SECONDS)
    except Exception:
        logger.warning("Semantic cache write failed; continuing without caching", exc_info=True)
