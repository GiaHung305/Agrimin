from app.workflow.state import AgentState
from app.workflow.confidence import compute_confidence, RELEVANT_DOCUMENT_THRESHOLD

# Ngưỡng này cần tinh chỉnh sau bằng Golden Dataset (Sprint 6.3).
RELEVANCE_THRESHOLD = RELEVANT_DOCUMENT_THRESHOLD


async def post_guardrail_node(state: AgentState) -> AgentState:
    require_citation = state["context"].get("require_citation", False)
    max_relevance = state["context"].get("max_relevance_score", 0)
    has_relevant_source = max_relevance >= RELEVANCE_THRESHOLD

    if require_citation and not has_relevant_source:
        state["confidence"] = 0.0
        state["guardrail_status"] = "block"
        return state

    state["confidence"] = compute_confidence(
        rerank_scores=state["context"].get("rerank_scores", []),
        reflection_notes=state.get("reflection_notes"),
        retry_count=state.get("retry_count", 0),
        weather_requested=state.get("plan", {}).get("need_weather", False),
        weather_available="weather" in state.get("tool_results", {}),
    )

    if state["confidence"] < 0.70:
        state["draft_answer"] += "\n\n(Lưu ý: tôi chưa hoàn toàn chắc chắn, bạn nên hỏi thêm cán bộ khuyến nông.)"

    state["guardrail_status"] = "pass"
    return state
