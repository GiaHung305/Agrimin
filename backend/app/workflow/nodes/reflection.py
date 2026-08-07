"""Typed answer reflection sharing the bounded internal-research retry budget."""

import json
import logging
from typing import Literal

from google.genai import types
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.model_registry import ModelRole
from app.services.model_gateway import generate_content
from app.workflow.state import AgentState

logger = logging.getLogger(__name__)


class ReflectionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["sufficient", "need_more_search"]
    missing_evidence: list[str] = Field(default_factory=list, max_length=4)


async def _call_gemini(prompt: str) -> ReflectionDecision:
    response = await generate_content(
        ModelRole.REFLECTION,
        prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ReflectionDecision,
        ),
    )
    return ReflectionDecision.model_validate_json(response.text or "")


def _bounded_missing_evidence(state: AgentState, values: list[str]) -> list[str]:
    candidates = values or state.get("missing_evidence", []) or state.get(
        "research_questions", []
    )
    return list(dict.fromkeys(
        " ".join(str(value).split()).strip()
        for value in candidates
        if str(value).strip()
    ))[:4]


async def reflection_node(state: AgentState) -> AgentState:
    docs_summary = "\n".join(
        f"[{index}] {document.get('source')}: {document.get('content', '')[:300]}"
        for index, document in enumerate(state.get("retrieved_docs", []), start=1)
    )
    research_summary = json.dumps(
        {
            "coverage": state.get("research_coverage", []),
            "missing_evidence": state.get("missing_evidence", []),
            "contradictions": state.get("evidence_conflicts", []),
            "stop_reason": state.get("research_stop_reason"),
        },
        ensure_ascii=False,
    )
    prompt = f"""Đánh giá câu trả lời có giải quyết câu hỏi và bám sát tài liệu không.
Nếu thiếu bằng chứng, trả về tối đa 4 câu hỏi tìm kiếm cụ thể trong missing_evidence.
Không yêu cầu tìm thêm chỉ vì cách viết có thể cải thiện.

Câu hỏi: {state['question']}
Câu trả lời đã sinh: {state.get('draft_answer')}
Trạng thái nghiên cứu: {research_summary}
Tài liệu đã dùng:
{docs_summary}"""
    try:
        decision = await _call_gemini(prompt)
    except ValidationError:
        logger.warning("Reflection returned invalid structured output; requesting more evidence")
        decision = ReflectionDecision(status="need_more_search")

    state["reflection_notes"] = decision.status
    if decision.status == "need_more_search":
        state["missing_evidence"] = _bounded_missing_evidence(
            state, decision.missing_evidence
        )
        # Retrieval retries happen before generation in research_analysis.
        # Starting a second generation after low/medium-risk tokens have been
        # streamed would violate the canonical SSE contract.
        state["research_stop_reason"] = "answer_insufficient"
    return state
