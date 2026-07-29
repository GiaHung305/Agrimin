from qdrant_client import AsyncQdrantClient
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings

qdrant_client = AsyncQdrantClient(url=settings.qdrant_url, timeout=10)

EMBEDDING_DIM = 1024


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5), reraise=True)
async def check_qdrant_connection() -> bool:
    try:
        await qdrant_client.get_collections()
        return True
    except Exception:
        return False