from app.workflow.state import AgentState


async def fallback_node(state: AgentState) -> AgentState:
    if state.get("retry_count", 0) >= 2:
        state["final_answer"] = "Tôi chưa tìm đủ thông tin để trả lời chắc chắn câu hỏi này. Bạn nên hỏi cán bộ khuyến nông địa phương."
    else:
        state["final_answer"] = "Câu hỏi này liên quan đến liều lượng/hóa chất, tôi chưa tìm được nguồn đủ tin cậy để trả lời chính xác. Bạn nên hỏi cán bộ khuyến nông địa phương."
    return state