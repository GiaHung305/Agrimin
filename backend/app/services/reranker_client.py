import httpx

from app.core.config import settings


async def rerank(query: str, documents: list[str]) -> list[float]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{settings.embedding_service_url}/rerank",
            json={"query": query, "documents": documents},
        )
        response.raise_for_status()
        return response.json()["scores"]