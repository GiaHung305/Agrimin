from app.workflow.state import AgentState

# bge-reranker-v2-m3 trả điểm dạng sigmoid (0-1). Điểm > 0.3 mới coi là thực sự liên quan.
# Đây là ngưỡng tạm, Sprint 4 sẽ tinh chỉnh chính xác bằng Golden Dataset.
RELEVANCE_THRESHOLD = 0.3


async def post_guardrail_node(state: AgentState) -> AgentState:
    require_citation = state["context"].get("require_citation", False)
    max_relevance = state["context"].get("max_relevance_score", 0)
    has_relevant_source = max_relevance > RELEVANCE_THRESHOLD

    if require_citation and not has_relevant_source:
        state["guardrail_status"] = "block"
        return state

    if state["confidence"] < 0.70:
        state["draft_answer"] += "\n\n(Lưu ý: tôi chưa hoàn toàn chắc chắn, bạn nên hỏi thêm cán bộ khuyến nông.)"

    state["guardrail_status"] = "pass"
    return state