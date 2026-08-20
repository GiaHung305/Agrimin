from app.workflow.state import AgentState


_CITATION_REASONS = {
    "missing_claim_citation",
    "invalid_claim_citation",
    "untraceable_claim_citation",
    "irrelevant_claim_citation",
    "non_authoritative_claim_citation",
}


async def fallback_node(state: AgentState) -> AgentState:
    """Return a safe fallback that matches the actual blocked capability."""
    reason = state.get("context", {}).get("guardrail_reason")
    # A fallback contains none of the generated claims, so its response must
    # not retain citations that belonged to the rejected draft.
    state["citations"] = []
    if state.get("visual_observations"):
        state["final_answer"] = (
            "Mình chưa có đủ bằng chứng truy vết để diễn giải ảnh này an toàn. "
            "Mình không kết luận bệnh chỉ từ ảnh; bạn có thể gửi thêm "
            "ảnh cận cảnh, tên cây, vị trí và thời gian xuất hiện triệu chứng."
        )
    elif state.get("retry_count", 0) >= 2:
        state["final_answer"] = (
            "Mình chưa tìm đủ thông tin để trả lời chắc chắn câu hỏi này. "
            "Bạn nên hỏi cán bộ khuyến nông địa phương."
        )
    elif reason in _CITATION_REASONS:
        state["final_answer"] = (
            "Mình chưa tìm được nguồn đủ phù hợp và truy vết được để trả lời "
            "chắc chắn. Bạn nên bổ sung thông tin hoặc hỏi cán bộ khuyến nông "
            "địa phương."
        )
    else:
        state["final_answer"] = (
            "Câu hỏi này có thể liên quan đến liều lượng hoặc hóa chất, nhưng "
            "mình chưa tìm được nguồn đủ tin cậy để trả lời chính xác. Bạn nên "
            "hỏi cán bộ khuyến nông địa phương."
        )
    return state
