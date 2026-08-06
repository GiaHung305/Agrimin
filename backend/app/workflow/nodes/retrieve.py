import asyncio

from app.workflow.state import AgentState
from app.retrieval.hybrid_search import hybrid_search
from app.tools.mcp_weather_client import get_weather_via_mcp, geocode_province_via_mcp


async def _retrieve_documents(question: str, need_rag: bool) -> list[dict]:
    return await hybrid_search(question, top_k=5) if need_rag else []


async def _retrieve_weather(need_weather: bool, province: str | None) -> dict | None:
    if not need_weather or not province:
        return None
    coords = await geocode_province_via_mcp(province)
    if not coords:
        return None
    lat, lon = coords
    return await get_weather_via_mcp(lat, lon)


async def retrieve_node(state: AgentState) -> AgentState:
    plan = state.get("plan") or {}
    results, weather = await asyncio.gather(
        _retrieve_documents(state["question"], plan.get("need_rag", True)),
        _retrieve_weather(
            plan.get("need_weather", False), state["context"].get("province")
        ),
    )

    state["retrieved_docs"] = [
        {
            "title": r.get("title"),
            "source": r.get("source") or "Không rõ nguồn",
            "content": r["content"],
        }
        for r in results
    ]

    max_score = max([r.get("rerank_score", 0) for r in results], default=0)
    state["context"]["max_relevance_score"] = max_score
    state["context"]["rerank_scores"] = [r.get("rerank_score", 0) for r in results]

    # Realtime Tool: Weather — gọi qua MCP Server (đúng boundary external, theo quyết định Sprint 0)
    state["tool_results"] = {"weather": weather} if weather else {}
    return state
