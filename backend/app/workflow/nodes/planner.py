from google import genai

from app.core.config import settings
from app.core.retry_utils import gemini_retry
from app.workflow.state import AgentState

client = genai.Client(api_key=settings.google_api_key)
MODEL_FAST = "gemini-3.1-flash-lite"


@gemini_retry
def _call_gemini(prompt: str):
    return client.models.generate_content(model=MODEL_FAST, contents=prompt)


async def planner_node(state: AgentState) -> AgentState:
    """
    Planner không trả lời, chỉ quyết định cần công cụ gì và mức độ rủi ro.
    Dùng model nhanh/rẻ vì đây là tác vụ classification.
    """
    prompt = f"""Bạn là bộ điều phối cho một AI nông nghiệp. Phân tích câu hỏi sau và trả lời CHÍNH XÁC theo định dạng:

need_rag: yes/no
need_weather: yes/no
risk_level: low/medium/high (high nếu liên quan thuốc BVTV, liều lượng, hóa chất)

Câu hỏi: {state['question']}
"""
    response = _call_gemini(prompt)
    text = response.text.lower()

    plan = {
        "need_rag": "yes" in text.split("need_rag:")[1][:10] if "need_rag:" in text else True,
        "need_weather": "yes" in text.split("need_weather:")[1][:10] if "need_weather:" in text else False,
    }
    risk_level = "low"
    if "risk_level:" in text:
        risk_part = text.split("risk_level:")[1][:10]
        if "high" in risk_part:
            risk_level = "high"
        elif "medium" in risk_part:
            risk_level = "medium"

    state["plan"] = plan
    state["risk_level"] = risk_level
    state["retry_count"] = 0
    return state