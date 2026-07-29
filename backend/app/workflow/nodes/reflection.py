from google import genai

from app.core.config import settings
from app.core.retry_utils import gemini_retry
from app.workflow.state import AgentState

client = genai.Client(api_key=settings.google_api_key)
MODEL_FAST = "gemini-3.1-flash-lite"


@gemini_retry
def _call_gemini(prompt: str):
    return client.models.generate_content(model=MODEL_FAST, contents=prompt)


async def reflection_node(state: AgentState) -> AgentState:
    """
    Tự kiểm tra: câu trả lời đã đủ dựa trên tài liệu chưa?
    Giới hạn retry_count để không lặp vô hạn khi tài liệu thực sự không đủ.
    """
    docs_summary = "\n".join([d["content"][:200] for d in state["retrieved_docs"]])

    prompt = f"""Câu hỏi: {state['question']}
Câu trả lời đã sinh: {state['draft_answer']}
Tài liệu đã dùng: {docs_summary}

Câu trả lời có đủ thông tin và bám sát tài liệu không? Trả lời CHỈ MỘT TỪ: "sufficient" hoặc "need_more_search"."""

    response = _call_gemini(prompt)
    text = response.text.strip().lower()

    if "sufficient" in text:
        state["reflection_notes"] = "sufficient"
    else:
        state["reflection_notes"] = "need_more_search"
        state["retry_count"] = state.get("retry_count", 0) + 1

    return state