from app.core.config import settings
from app.core.ai_service_client import get_ai_service_client

EMBEDDING_SERVICE_URL = settings.embedding_service_url

async def embed_batch(texts: list[str]) -> list[list[float]]:
    """Create embeddings through the dedicated CPU/GPU model service."""
    response = await get_ai_service_client().post(
        f"{EMBEDDING_SERVICE_URL}/embed",
        json={"texts": texts},
    )
    response.raise_for_status()
    data = response.json()
    return data["embeddings"]


async def embed_text(text: str) -> list[float]:
    result = await embed_batch([text])
    return result[0]
