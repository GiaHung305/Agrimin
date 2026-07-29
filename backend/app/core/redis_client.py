import redis.asyncio as redis
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.config import settings

redis_client = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5,
    retry_on_timeout=True,
)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type(redis.ConnectionError),
    reraise=True,
)
async def safe_redis_get(key: str):
    """Wrapper an toàn — nếu Redis chết, gọi hàm này sẽ raise sau 3 lần thử,
    cho phép code gọi nó tự quyết định graceful degradation (bỏ qua cache)."""
    return await redis_client.get(key)


async def check_redis_connection() -> bool:
    try:
        return await redis_client.ping()
    except Exception:
        return False