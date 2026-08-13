"""Deterministic summary for observation-only vision requests."""

from __future__ import annotations

from app.workflow.state import AgentState


_PART_LABELS = {
    "leaf": "lá",
    "stem": "thân",
    "fruit": "quả",
    "flower": "hoa",
    "root": "rễ",
    "whole_plant": "toàn cây",
    "multiple": "nhiều bộ phận",
    "unknown": "bộ phận chưa xác định",
}
_LIMITATION_LABELS = {
    "low_light": "thiếu sáng",
    "overexposed": "quá sáng",
    "blur": "ảnh mờ",
    "occlusion": "bị che khuất",
    "too_far": "chụp quá xa",
    "single_view": "chỉ có một góc chụp",
    "background_clutter": "nền ảnh gây nhiễu",
    "unknown_crop": "chưa đủ dấu hiệu xác định cây",
}


def _observation_text(observation: dict, index: int) -> str:
    crop = str(observation.get("crop_candidate") or "").strip()
    part = _PART_LABELS.get(
        str(observation.get("plant_part") or "unknown"),
        "bộ phận chưa xác định",
    )
    lines = [f"Ảnh {index}: quan sát thấy {part} của cây."]
    if crop:
        lines.append(
            f"Cây có thể là {crop}, nhưng đây chỉ là nhận dạng sơ bộ từ ảnh."
        )
    else:
        lines.append("Chưa đủ dấu hiệu trực quan để xác định loại cây.")
    descriptions = [
        " ".join(str(item.get("description") or "").split())
        for item in observation.get("visible_symptoms", [])
        if str(item.get("description") or "").strip()
    ]
    if descriptions:
        lines.append("Đặc điểm nhìn thấy: " + "; ".join(descriptions) + ".")
    else:
        lines.append("Không thấy đặc điểm bất thường rõ ràng trong góc ảnh này.")
    limitations = [
        _LIMITATION_LABELS[item]
        for item in observation.get("limitations", [])
        if item in _LIMITATION_LABELS
    ]
    if limitations:
        lines.append("Giới hạn quan sát: " + ", ".join(limitations) + ".")
    return " ".join(lines)


async def objective_visual_summary_node(state: AgentState) -> AgentState:
    observations = state.get("visual_observations", [])
    state["plan"] = {
        "need_rag": False,
        "need_weather": False,
        "need_deep_research": False,
        "research_questions": [],
        "need_vision": True,
        "vision_available": bool(observations),
    }
    state["risk_level"] = "low"
    state["retrieved_docs"] = []
    state["answer_evidence"] = []
    state["citations"] = []
    state["research_questions"] = []
    state["research_coverage"] = []
    state["missing_evidence"] = []
    state["evidence_conflicts"] = []
    state["research_stop_reason"] = "no_research_required"
    state["reflection_notes"] = None
    state["retry_count"] = 0
    state["context"]["require_citation"] = False
    summaries = [
        _observation_text(observation, index)
        for index, observation in enumerate(observations, start=1)
    ]
    state["draft_answer"] = (
        " ".join(summaries)
        + " Tôi chỉ mô tả đặc điểm nhìn thấy và không chẩn đoán bệnh từ ảnh."
    )
    return state
