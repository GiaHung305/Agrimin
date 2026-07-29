import hashlib
import json

from app.core.redis_client import redis_client
from app.services.embedding_client import embed_text

CACHE_TTL_SECONDS = 3600  # 1 giờ — câu trả lời nông nghiệp không đổi nhanh như thời tiết
SIMILARITY_THRESHOLD = 0.95  # ngưỡng cosine similarity để coi là "cùng câu hỏi"


def _context_key(province: str | None, crop: str | None) -> str:
    """Cache theo cả context, không chỉ theo câu hỏi — tránh trả lời sai ngữ cảnh."""
    province = (province or "unknown").lower().strip()
    crop = (crop or "unknown").lower().strip()
    return f"{province}:{crop}"


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


async def get_cached_answer(question: str, province: str | None, crop: str | None) -> dict | None:
    """
    Graceful degradation: nếu Redis chết, trả về None (coi như cache miss)
    thay vì để lỗi lan ra làm sập cả /chat — đúng bài học từ sự cố Redis hôm nay.
    """
    try:
        context_key = _context_key(province, crop)
        index_key = f"semcache_index:{context_key}"

        cached_index_raw = await redis_client.get(index_key)
        if not cached_index_raw:
            return None

        query_vector = await embed_text(question)
        cached_index = json.loads(cached_index_raw)

        for entry in cached_index:
            similarity = _cosine_similarity(query_vector, entry["vector"])
            if similarity >= SIMILARITY_THRESHOLD:
                answer_raw = await redis_client.get(f"semcache_answer:{entry['hash']}")
                if answer_raw:
                    result = json.loads(answer_raw)
                    result["from_cache"] = True
                    return result

        return None
    except Exception as e:
        print(f"[WARNING] Semantic Cache lookup thất bại (Redis có thể đang down): {e}")
        return None


async def store_answer(question: str, province: str | None, crop: str | None, answer_data: dict):
    """
    Graceful degradation: nếu Redis chết lúc lưu cache, chỉ log cảnh báo,
    KHÔNG raise lỗi — vì thất bại lưu cache không nên làm hỏng response đã có cho user.
    """
    try:
        context_key = _context_key(province, crop)
        index_key = f"semcache_index:{context_key}"

        query_vector = await embed_text(question)
        question_hash = hashlib.sha256(question.encode()).hexdigest()[:16]

        await redis_client.set(
            f"semcache_answer:{question_hash}",
            json.dumps(answer_data, ensure_ascii=False),
            ex=CACHE_TTL_SECONDS,
        )

        cached_index_raw = await redis_client.get(index_key)
        cached_index = json.loads(cached_index_raw) if cached_index_raw else []
        cached_index.append({"hash": question_hash, "vector": query_vector})

        cached_index = cached_index[-50:]

        await redis_client.set(index_key, json.dumps(cached_index), ex=CACHE_TTL_SECONDS)
    except Exception as e:
        print(f"[WARNING] Semantic Cache lưu thất bại (Redis có thể đang down): {e}")