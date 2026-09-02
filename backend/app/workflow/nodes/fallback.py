from app.workflow.state import AgentState


_CITATION_REASONS = {
    "missing_claim_citation",
    "invalid_claim_citation",
    "untraceable_claim_citation",
    "irrelevant_claim_citation",
    "non_authoritative_claim_citation",
    "uncited_technical_claim",
    "unsupported_claim_evidence",
    "insufficient_answer_evidence",
}

_MISSING_WEATHER_DATA = "missing_deterministic_weather_data"
_MISSING_SAFETY_CONTEXT = "missing_safety_context"
_UNSUPPORTED_DOSAGE = "unsupported_numeric_dosage"


async def fallback_node(state: AgentState) -> AgentState:
    """Return a safe fallback that matches the actual blocked capability."""
    context = state.setdefault("context", {})
    reason = context.get("guardrail_reason")
    # A fallback contains none of the generated claims. Remove the rejected
    # material as well as its metadata so it cannot leak through a serializer,
    # checkpoint continuation, or a future response path.
    state["draft_answer"] = None
    state["citations"] = []
    state["answer_evidence"] = []
    state["pending_action"] = None
    state["confidence"] = 0.0
    state["guardrail_status"] = "block"

    if reason == _MISSING_WEATHER_DATA:
        context["user_response_kind"] = "weather_unavailable"
        state["final_answer"] = (
            "Mình chưa lấy được dữ liệu dự báo hợp lệ cho địa điểm và thời gian "
            "bạn hỏi. Bạn hãy kiểm tra lại tên tỉnh/thành hoặc thử lại sau ít "
            "phút."
        )
    elif reason == _MISSING_SAFETY_CONTEXT:
        context["user_response_kind"] = "abstention"
        state["final_answer"] = (
            "Mình chưa thể đưa liều dùng an toàn khi còn thiếu thông tin quyết "
            "định liều. Bạn hãy gửi ảnh nhãn, hoặc ghi rõ tên sản phẩm hoặc hoạt "
            "chất, cây trồng, giai đoạn cây và cỡ bình hay diện tích xử lý để "
            "mình đối chiếu đúng hướng dẫn; với phân bón đất, hãy thêm kết quả "
            "phân tích đất nếu có."
        )
    elif reason == _UNSUPPORTED_DOSAGE:
        context["user_response_kind"] = "abstention"
        state["final_answer"] = (
            "Mình chưa xác minh được liều dùng từ nhãn sản phẩm hoặc nguồn chính "
            "thức nên sẽ không đoán con số. Bạn hãy gửi ảnh nhãn rõ phần liều "
            "dùng, tên cây và cỡ bình phun để mình kiểm tra lại."
        )
    elif state.get("visual_observations"):
        context["user_response_kind"] = "abstention"
        state["final_answer"] = (
            "Ảnh hiện tại chưa đủ để xác định nguyên nhân một cách đáng tin cậy. "
            "Mình không kết luận bệnh chỉ từ ảnh; bạn hãy gửi thêm ảnh toàn cây, "
            "hai mặt lá, tên cây, vị trí và thời gian xuất hiện triệu chứng."
        )
    elif reason in _CITATION_REASONS:
        context["user_response_kind"] = "abstention"
        state["final_answer"] = (
            "Mình chưa tìm được nguồn đủ phù hợp để trả lời chắc chắn. Bạn hãy "
            "bổ sung tên cây, giai đoạn sinh trưởng, triệu chứng và địa phương; "
            "nếu cần xử lý ngay, hãy hỏi cán bộ khuyến nông tại địa phương."
        )
    elif state.get("retry_count", 0) >= 2:
        context["user_response_kind"] = "abstention"
        state["final_answer"] = (
            "Mình chưa có đủ thông tin đáng tin cậy để trả lời câu hỏi này. Bạn "
            "hãy bổ sung tình trạng cây và địa phương, hoặc hỏi cán bộ khuyến "
            "nông tại địa phương nếu cần xử lý ngay."
        )
    else:
        context["user_response_kind"] = "abstention"
        state["final_answer"] = (
            "Mình chưa có đủ căn cứ đáng tin cậy để trả lời chính xác câu hỏi "
            "này. Bạn hãy bổ sung thông tin cụ thể hơn; nếu cần xử lý ngay, hãy "
            "hỏi cán bộ khuyến nông tại địa phương."
        )
    return state
