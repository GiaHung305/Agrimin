from app.core.config import settings
from app.core.ai_service_client import get_ai_service_client


def _validated_scores(payload: dict) -> list:
    if payload.get("model") != settings.reranker_model:
        raise RuntimeError("reranker response model does not match runtime settings")
    return payload["scores"]


async def rerank(query: str, documents: list[str]) -> list[float]:
    response = await get_ai_service_client().post(
        f"{settings.embedding_service_url}/rerank",
        json={
            "query": query,
            "documents": documents,
            "expected_model": settings.reranker_model,
        },
    )
    response.raise_for_status()
    return _validated_scores(response.json())


async def rerank_many(
    items: list[tuple[str, list[str]]],
) -> list[list[float]]:
    """Rerank independent queries in one bounded CPU inference batch."""
    if not items:
        return []
    response = await get_ai_service_client().post(
        f"{settings.embedding_service_url}/rerank/batch",
        json={
            "expected_model": settings.reranker_model,
            "items": [
                {"query": query, "documents": documents}
                for query, documents in items
            ]
        },
    )
    response.raise_for_status()
    return _validated_scores(response.json())
