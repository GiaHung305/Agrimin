"""Structured extraction of user-owned farm facts after guardrail PASS."""

import json
import logging
import re
import unicodedata
from typing import Literal

from google.genai import types
from google.genai.errors import ServerError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.model_registry import ModelRole
from app.persistence.models import MemoryFact
from app.services.model_gateway import ModelProviderUnavailable, generate_content
from app.workflow.state import AgentState

logger = logging.getLogger(__name__)
_PERSONAL_CONTEXT_PATTERN = re.compile(r"\b(toi|minh|chung toi)\b")
MemoryFieldName = Literal["province", "crop", "area_ha", "farming_style"]


class MemoryExtraction(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
        str_strip_whitespace=True,
    )

    has_personal_info: bool
    province: str | None = Field(default=None, min_length=1, max_length=120)
    crop: str | None = Field(default=None, min_length=1, max_length=120)
    area_ha: float | None = Field(default=None, gt=0)
    farming_style: str | None = Field(default=None, min_length=1, max_length=120)
    clear_fields: list[MemoryFieldName] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def validate_personal_info_flag(self):
        extracted_fields = {
            name
            for name in ("province", "crop", "area_ha", "farming_style")
            if getattr(self, name) is not None
        }
        clear_fields = set(self.clear_fields)
        if len(clear_fields) != len(self.clear_fields):
            raise ValueError("clear_fields must not contain duplicates")
        if extracted_fields & clear_fields:
            raise ValueError("a field cannot be both set and cleared")
        if self.has_personal_info != bool(extracted_fields or clear_fields):
            raise ValueError(
                "has_personal_info must match set or cleared fields"
            )
        return self


async def _call_gemini(prompt: str) -> MemoryExtraction:
    response = await generate_content(
        ModelRole.MEMORY,
        prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=MemoryExtraction.model_json_schema(),
        ),
    )
    return MemoryExtraction.model_validate_json(response.text or "")


def _may_contain_user_owned_fact(question: str) -> bool:
    normalized = "".join(
        char
        for char in unicodedata.normalize("NFD", question.casefold())
        if unicodedata.category(char) != "Mn"
    ).replace("đ", "d")
    return bool(_PERSONAL_CONTEXT_PATTERN.search(normalized))


async def memory_extract_node(state: AgentState, db: AsyncSession) -> AgentState:
    if state.get("guardrail_status") != "pass":
        return state
    if state.get("context", {}).get("deterministic_safe_response"):
        return state
    if (
        state.get("context", {})
        .get("action_request", {})
        .get("intent", "none")
        != "none"
    ):
        return state
    if not _may_contain_user_owned_fact(state.get("question", "")):
        return state

    prompt = f"""Đọc câu hỏi sau, chỉ trích xuất thông tin người dùng khẳng định rõ
về chính họ hoặc nông trại của họ (tỉnh, cây trồng, diện tích tính bằng ha,
phương pháp canh tác). Không suy diễn, không chép giá trị bị phủ định, giả định,
hỏi lại hoặc chỉ là đề xuất vào các trường dữ liệu. Khi người dùng nói rõ họ
không còn áp dụng một fact cũ, thêm tên trường tương ứng vào clear_fields; không
đồng thời đặt giá trị và xóa cùng một trường. Nếu không có trường hợp lệ, đặt
has_personal_info=false, clear_fields=[] và mọi trường còn lại là null. Chỉ đặt
has_personal_info=true khi có ít nhất một giá trị hoặc một trường cần xóa.

Câu hỏi: {state['question']}"""
    try:
        extraction = await _call_gemini(prompt)
    except ValidationError:
        logger.warning("Memory extractor returned invalid structured output; skipping write")
        return state
    except (ModelProviderUnavailable, ServerError):
        logger.warning("Optional memory extractor is unavailable; skipping write")
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
