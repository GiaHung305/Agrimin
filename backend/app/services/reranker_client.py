from app.core.config import settings
from app.core.ai_service_client import get_ai_service_client


async def rerank(query: str, documents: list[str]) -> list[float]:
    response = await get_ai_service_client().post(
        f"{settings.embedding_service_url}/rerank",
        json={"query": query, "documents": documents},
    )
    response.raise_for_status()
    return response.json()["scores"]
