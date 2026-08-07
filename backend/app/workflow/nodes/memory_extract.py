"""Structured extraction of user-owned farm facts after guardrail PASS."""

import json
import logging

from google.genai import types
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.model_registry import ModelRole
from app.repository.models import MemoryFact
from app.services.model_gateway import generate_content
from app.workflow.state import AgentState

logger = logging.getLogger(__name__)


class MemoryExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    has_personal_info: bool
    province: str | None = None
    crop: str | None = None
    area_ha: float | None = None
    farming_style: str | None = None


async def _call_gemini(prompt: str) -> MemoryExtraction:
    response = await generate_content(
        ModelRole.MEMORY,
        prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=MemoryExtraction,
        ),
    )
    return MemoryExtraction.model_validate_json(response.text or "")


async def memory_extract_node(state: AgentState, db: AsyncSession) -> AgentState:
    if state.get("guardrail_status") != "pass":
        return state

    prompt = f"""Đọc câu hỏi sau, trích xuất thông tin cá nhân về người dùng nếu có
(vùng miền/tỉnh, loại cây trồng, diện tích tính bằng ha, phương pháp canh tác).
Nếu không có trường nào, để null.

Câu hỏi: {state['question']}"""
    try:
        extraction = await _call_gemini(prompt)
    except ValidationError:
        logger.warning("Memory extractor returned invalid structured output; skipping write")
        return state

    if extraction.has_personal_info:
        fact = MemoryFact(
            user_id=state["user_id"],
            fact_text=json.dumps(extraction.model_dump(), ensure_ascii=False),
            confidence=state["confidence"],
        )
        db.add(fact)
        await db.commit()
    return state
