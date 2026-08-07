"""Gate multimodal requests before any model call."""

from __future__ import annotations

import re

from app.workflow.state import AgentState

_IMAGE_DEPENDENT_PATTERN = re.compile(
    r"\b(ảnh|hình|lá này|bị gì|bệnh gì|chẩn đoán)\b",
    re.IGNORECASE,
)

_QUALITY_GUIDANCE = {
    "low_resolution": "chụp gần hơn và dùng độ phân giải cao hơn",
    "too_dark": "chụp lại ở nơi đủ sáng",
    "overexposed": "tránh ánh sáng gắt hoặc phản chiếu trực tiếp",
    "blurry_or_low_detail": "giữ máy chắc và lấy nét vào vùng có triệu chứng",
}


def route_after_image_quality(state: AgentState) -> str:
    return "stop" if state.get("context", {}).get("vision_stop") else "continue"


async def image_quality_guard_node(state: AgentState) -> AgentState:
    observations = state.get("image_observations", [])
    if not observations:
        return state

    context = state.setdefault("context", {})
    usable = [item for item in observations if item.get("usable_for_vision")]
    if not usable:
        issue_codes = list(dict.fromkeys(
            issue
            for observation in observations
            for issue in observation.get("quality_issues", [])
        ))
        guidance = "; ".join(
            _QUALITY_GUIDANCE[issue]
            for issue in issue_codes
            if issue in _QUALITY_GUIDANCE
        )
        state["final_answer"] = (
            "Ảnh hiện chưa đủ chất lượng để phân tích an toàn. Vui lòng "
            f"{guidance or 'chụp lại ảnh rõ hơn'}, đồng thời cho biết cây trồng, "
            "bộ phận bị ảnh hưởng và triệu chứng kéo dài bao lâu."
        )
        state["guardrail_status"] = "block"
        state["confidence"] = 0.0
        context["vision_stop"] = "image_quality_insufficient"
        return state

    if _IMAGE_DEPENDENT_PATTERN.search(state["question"]):
        visual_observations = state.get("visual_observations", [])
        relevant = [
            item
            for item in visual_observations
            if item.get("relevance") == "agriculture_plant"
            and float(item.get("confidence") or 0.0) >= 0.60
        ]
        if relevant:
            return state

        if visual_observations:
            out_of_domain = all(
                item.get("relevance") == "out_of_domain"
                for item in visual_observations
            )
            state["final_answer"] = (
                "Ảnh không cho thấy đối tượng cây trồng phù hợp để phân tích. Vui lòng "
                "gửi ảnh rõ phần cây hoặc lá cần kiểm tra."
                if out_of_domain
                else "Tôi chưa đủ chắc chắn ảnh thể hiện cây trồng hoặc triệu chứng nào. "
                "Vui lòng chụp gần vùng bất thường và cho biết cây trồng, bộ phận bị ảnh "
                "hưởng cùng thời gian xuất hiện."
            )
            context["vision_stop"] = (
                "image_irrelevant" if out_of_domain else "vision_observation_uncertain"
            )
        elif context.get("vision_error") in {
            "timeout",
            "unavailable",
            "invalid_output",
            "unsafe_output",
        }:
            state["final_answer"] = (
                "Ảnh đã đạt yêu cầu kỹ thuật nhưng dịch vụ phân tích thị giác hiện chưa "
                "khả dụng an toàn. Tôi sẽ không đoán bệnh từ ảnh; vui lòng mô tả cây, "
                "triệu chứng và thời gian xuất hiện để tôi tra cứu bằng chứng."
            )
            context["vision_stop"] = "vision_analyzer_unavailable"
        else:
            state["final_answer"] = (
                "Ảnh đã đạt yêu cầu kỹ thuật, nhưng phiên bản hiện tại chưa bật mô hình "
                "phân tích hình ảnh nên tôi sẽ không đoán bệnh từ ảnh. Hãy mô tả cây trồng, "
                "vị trí triệu chứng, màu sắc, hình dạng và thời gian xuất hiện; tôi sẽ tra "
                "tài liệu phù hợp trong lúc tính năng thị giác được đánh giá an toàn."
            )
            context["vision_stop"] = "vision_model_not_enabled"
        state["guardrail_status"] = "block"
        state["confidence"] = 0.0
    return state
