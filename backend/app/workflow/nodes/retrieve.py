from app.workflow.state import AgentState
from app.retrieval.hybrid_search import hybrid_search
from app.tools.mcp_weather_client import get_weather_via_mcp, geocode_province_via_mcp


async def retrieve_node(state: AgentState) -> AgentState:
    results = await hybrid_search(state["question"], top_k=5)

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

    # Realtime Tool: Weather — gọi qua MCP Server (đúng boundary external, theo quyết định Sprint 0)
    tool_results = {}
    if state["plan"].get("need_weather"):
        province = state["context"].get("province")
        if province:
            coords = await geocode_province_via_mcp(province)
            if coords:
                lat, lon = coords
                tool_results["weather"] = await get_weather_via_mcp(lat, lon)

    state["tool_results"] = tool_results
    return state