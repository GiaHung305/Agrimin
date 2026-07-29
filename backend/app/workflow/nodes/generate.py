from google import genai

from app.core.config import settings
from app.core.retry_utils import gemini_retry
from app.workflow.state import AgentState

client = genai.Client(api_key=settings.google_api_key)
MODEL_STRONG = "gemini-3.5-flash"


@gemini_retry
def _call_gemini(prompt: str):
    return client.models.generate_content(model=MODEL_STRONG, contents=prompt)


async def generate_node(state: AgentState) -> AgentState:
    docs_text = "\n".join([d["content"] for d in state["retrieved_docs"]])
    known_facts = state["context"].get("known_facts", [])
    facts_text = "\n".join(str(f) for f in known_facts) if known_facts else "Chưa có thông tin."

    weather_text = "Không có dữ liệu thời tiết."
    if "weather" in state["tool_results"]:
        weather_text = str(state["tool_results"]["weather"]["forecast"])

    prompt = f"""Bạn là chuyên gia nông nghiệp Việt Nam. Trả lời câu hỏi dựa trên tài liệu sau:

Tài liệu:
{docs_text}

Thông tin đã biết về người dùng:
{facts_text}

Dữ liệu thời tiết 3 ngày tới:
{weather_text}

Câu hỏi: {state['question']}

Trả lời ngắn gọn, chính xác, có xét đến thông tin về người dùng và thời tiết nếu liên quan."""

    response = _call_gemini(prompt)

    state["draft_answer"] = response.text
    state["citations"] = [d["source"] for d in state["retrieved_docs"]]
    state["confidence"] = 0.8
    return state