import hashlib
import json
import logging
import re
from datetime import datetime, timezone

from app.core.redis_client import redis_client
from app.core.model_registry import runtime_fingerprint
from app.retrieval.text_normalization import normalize_vietnamese
from app.services.embedding_client import embed_text
from app.workflow.question_freshness import is_realtime_sensitive_question

CACHE_TTL_SECONDS = 3600
SIMILARITY_THRESHOLD = 0.95
CORPUS_VERSION_KEY = "semantic_cache:corpus_version"
SEMANTIC_CACHE_KEY_VERSION = "v4"
logger = logging.getLogger(__name__)

_QUESTION_INTENT_PATTERNS = (
    (
        "cause",
        re.compile(r"\b(?:nguyen nhan|vi sao|tai sao|do dau)\b"),
    ),
    (
        "identification",
        re.compile(
            r"\b(?:dau hieu|trieu chung|nhan biet|phan biet|"
            r"bi gi|benh gi|chan doan)\b"
        ),
    ),
    (
        "treatment",
        re.compile(
            r"\b(?:xu ly|khac phuc|lam gi|nen lam|giai phap|"
            r"lam sao|cach chua|cach tri|xu tri|dieu tri)\b"
        ),
    ),
    (
        "prevention",
        re.compile(
            r"\b(?:phong ngua|phong tranh|phong benh|phong tru|"
            r"cach phong|ngan ngua|han che)\b"
        ),
    ),
    (
        "definition",
        re.compile(r"\b(?:la gi|the nao la|khai niem|y nghia)\b"),
    ),
    (
        "timing",
        re.compile(r"\b(?:khi nao|bao lau|thoi diem)\b"),
    ),
    (
        "comparison",
        re.compile(r"\b(?:so sanh|khac nhau|giong nhau)\b"),
    ),
    (
        "crop_care",
        re.compile(
            r"\b(?:cham soc|tuoi nuoc|tia canh|xuong giong|thu hoach)\b"
        ),
    ),
)
_YES_NO_PATTERN = re.compile(r"\b(?:co|nen|can|phai) .{0,80} khong\b")
_NEGATIVE_CONSTRAINT_PATTERN = re.compile(
    r"\b(?:khong nen|khong duoc|khong can|tranh|loai bo|"
    r"khong (?:su dung|dung|tuoi|bon|phun|cat|tia|thu hoach|xu ly))\b"
)
_SAFETY_EXCLUSION_PATTERN = re.compile(
    r"\bkhong\s+(?:dua(?: ra)?|tu van|de xuat|neu|cung cap|"
    r"noi ve|de cap|su dung|dung)\s+"
    r"(?:bat ky\s+)?(?:thuoc|hoa chat|lieu(?: luong)?|pha(?: tron)?|"
    r"nong do|xu ly|phac do)\b"
)


def question_signature(question: str) -> str:
    """Return privacy-safe labels that prevent cross-intent cache collisions."""
    normalized = " ".join(normalize_vietnamese(question).split())
    intents = [
        label
        for label, pattern in _QUESTION_INTENT_PATTERNS
        if pattern.search(normalized)
    ] or ["general"]
    return json.dumps(
        {
            "intents": intents,
            "negative_constraint": bool(
                _NEGATIVE_CONSTRAINT_PATTERN.search(normalized)
            ),
            "safety_exclusion": bool(_SAFETY_EXCLUSION_PATTERN.search(normalized)),
            "yes_no": bool(_YES_NO_PATTERN.search(normalized)),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _context_key(
    user_id: str,
    province: str | None,
    crop: str | None,
    *,
    time_window: str | None = None,
    farm_profile: dict | None = None,
    known_facts: list[dict] | None = None,
) -> str:
    """Hash every private context input that can materially change an answer."""
    user_hash = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:16]
    province = (province or "unknown").lower().strip()
    crop = (crop or "unknown").lower().strip()
    # DB row order must not create cache misses for the same set of facts.
    canonical_facts = sorted(
        json.dumps(
            fact,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for fact in (known_facts or [])
    )
    context_payload = json.dumps(
        {
            "farm_context": farm_profile or {},
            "known_facts": canonical_facts,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    context_hash = hashlib.sha256(
        context_payload.encode("utf-8")
    ).hexdigest()[:16]
    time_window = time_window or datetime.now(timezone.utc).strftime("%Y%m%d%H")
    return (
        f"{SEMANTIC_CACHE_KEY_VERSION}:{runtime_fingerprint()}:"
        f"{time_window}:{user_hash}:{province}:{crop}:context-{context_hash}"
    )


async def _versioned_context_key(
    user_id: str,
    province: str | None,
    crop: str | None,
    farm_profile: dict | None = None,
    known_facts: list[dict] | None = None,
) -> str:
    """Include the mutable evidence version so new documents invalidate answers."""
    corpus_version = await redis_client.get(CORPUS_VERSION_KEY) or "0"
    context_key = _context_key(
        user_id,
        province,
        crop,
        farm_profile=farm_profile,
        known_facts=known_facts,
    )
    return (
        f"{context_key}:corpus-{corpus_version}"
    )


async def bump_semantic_cache_corpus_version() -> None:
    """Invalidate semantic-cache namespaces after evidence metadata changes."""
    try:
        await redis_client.incr(CORPUS_VERSION_KEY)
    except Exception:
        logger.warning(
            "Unable to bump semantic-cache corpus version; cached answers retain their TTL",
            exc_info=True,
        )


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
    farm_profile: dict | None = None,
    known_facts: list[dict] | None = None,
) -> dict | None:
    """Return a matching answer, treating cache/embedding failures as a miss."""
    try:
        index_key = (
            "semcache_index:"
            f"{await _versioned_context_key(user_id, province, crop, farm_profile, known_facts)}"
        )
        cached_index_raw = await redis_client.get(index_key)
        if not cached_index_raw:
            return None

        query_vector = await embed_text(question)
        query_signature = question_signature(question)
        for entry in json.loads(cached_index_raw):
            # Reject v2/legacy entries and semantically close questions whose
            # requested task or polarity differs from the current question.
            if entry.get("question_signature") != query_signature:
                continue
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
    farm_profile: dict | None = None,
    known_facts: list[dict] | None = None,
):
    """Store an answer opportunistically without failing the chat response."""
    try:
        context_key = await _versioned_context_key(
            user_id, province, crop, farm_profile, known_facts
        )
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
        cached_index.append(
            {
                "answer_key": answer_key,
                "vector": query_vector,
                "question_signature": question_signature(question),
            }
        )
        await redis_client.set(index_key, json.dumps(cached_index[-50:]), ex=CACHE_TTL_SECONDS)
    except Exception:
        logger.warning("Semantic cache write failed; continuing without caching", exc_info=True)
