import json

from google import genai
from google.genai import types
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.retry_utils import gemini_retry
from app.workflow.state import AgentState
from app.repository.models import MemoryFact

client = genai.Client(api_key=settings.google_api_key)
MODEL_FAST = "gemini-3.1-flash-lite"

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "has_personal_info": {"type": "boolean"},
        "province": {"type": "string", "nullable": True},
        "crop": {"type": "string", "nullable": True},
        "area_ha": {"type": "number", "nullable": True},
        "farming_style": {"type": "string", "nullable": True},
    },
    "required": ["has_personal_info"],
}


@gemini_retry
def _call_gemini(prompt: str):
    return client.models.generate_content(
        model=MODEL_FAST,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=EXTRACT_SCHEMA,
        ),
    )


async def memory_extract_node(state: AgentState, db: AsyncSession) -> AgentState:
    prompt = f"""Đọc câu hỏi sau, trích xuất thông tin cá nhân về người dùng nếu có
(vùng miền/tỉnh, loại cây trồng, diện tích tính bằng ha, phương pháp canh tác).
Nếu không có trường nào, để null.

Câu hỏi: {state['question']}"""

    response = _call_gemini(prompt)
    data = json.loads(response.text)

    if data.get("has_personal_info"):
        fact = MemoryFact(
            user_id=state["user_id"],
            fact_text=json.dumps(data, ensure_ascii=False),
            confidence=0.85,
        )
        db.add(fact)
        await db.commit()

    return state