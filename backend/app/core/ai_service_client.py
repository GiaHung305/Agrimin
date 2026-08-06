import httpx

_client: httpx.AsyncClient | None = None


def get_ai_service_client() -> httpx.AsyncClient:
    """Return the shared keep-alive pool for embedding and reranking calls."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
        )
    return _client


async def close_ai_service_client() -> None:
    global _client
    client = _client
    _client = None
    if client is not None and not client.is_closed:
        await client.aclose()
