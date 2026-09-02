"""Typed answer reflection sharing the bounded internal-research retry budget."""

import json
import logging
import re
from typing import Literal

from google.genai import types
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.model_registry import ModelRole
from app.services.model_gateway import generate_content
from app.workflow.citation_integrity import (
    prune_exact_rejected_claims,
    prune_rejected_claim_ids,
    referenced_evidence_indexes,
    technical_claim_units,
)
from app.workflow.state import AgentState

logger = logging.getLogger(__name__)


class ReflectionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["sufficient", "need_more_search"]
    missing_evidence: list[str] = Field(default_factory=list, max_length=4)
    unsupported_claims: list[str] = Field(default_factory=list, max_length=4)
    unsupported_claim_ids: list[int] = Field(default_factory=list, max_length=4)


_CITATION_MARKER_PATTERN = re.compile(r"\[E(\d+)\]", re.IGNORECASE)


async def _call_gemini(prompt: str) -> ReflectionDecision:
    response = await generate_content(
        ModelRole.REFLECTION,
        prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=ReflectionDecision.model_json_schema(),
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


def _cited_evidence_summary(state: AgentState) -> str:
    """Show the judge the exact chunks referenced by the generated answer."""
    documents = state.get("answer_evidence", state.get("retrieved_docs", []))
    cited_indexes = list(dict.fromkeys(
        int(value)
        for value in _CITATION_MARKER_PATTERN.findall(
            state.get("draft_answer") or ""
        )
    ))
    indexes = cited_indexes or list(range(1, min(len(documents), 5) + 1))
    summaries = []
    for index in indexes[:8]:
        if not 1 <= index <= len(documents):
            continue
        document = documents[index - 1]
        summaries.append(
            f"[E{index}] {document.get('source')}: "
            f"{document.get('content', '')[:1200]}"
        )
    return "\n\n".join(summaries) or "Không có tài liệu được trích dẫn."


def _numbered_claim_summary(state: AgentState) -> tuple[list[str], str]:
    claims = technical_claim_units(state.get("draft_answer"))
    summary = "\n".join(
        f"[C{index}] {claim}" for index, claim in enumerate(claims, start=1)
    )
    return claims, summary or "Không có claim chuyên môn cần kiểm tra."


async def reflection_node(state: AgentState) -> AgentState:
    if (
        state.get("context", {}).get("deterministic_action_response")
        or state.get("context", {}).get("deterministic_safe_response")
        or state.get("plan", {}).get("direct_saved_farm_fact", False)
    ):
        state["reflection_notes"] = "sufficient"
        return state

    context = state.setdefault("context", {})
    is_prune_recheck = bool(context.pop("reflection_recheck_required", False))
    if is_prune_recheck:
        context["unsupported_claim_recheck_attempted"] = True
    context.pop("claim_entailment_failed", None)
    context.pop("unsupported_claim_count", None)
    context.pop("unsupported_claims", None)
    context.pop("unsupported_claim_ids", None)
    docs_summary = _cited_evidence_summary(state)
    numbered_claims, numbered_claims_summary = _numbered_claim_summary(state)
    research_summary = json.dumps(
        {
            "coverage": state.get("research_coverage", []),
            "missing_evidence": state.get("missing_evidence", []),
            "contradictions": state.get("evidence_conflicts", []),
            "stop_reason": state.get("research_stop_reason"),
        },
        ensure_ascii=False,
    )
    prompt = f"""Đánh giá câu trả lời có giải quyết câu hỏi và được các đoạn tài
liệu trích dẫn hỗ trợ hay không. Kiểm tra từng claim chuyên môn với đúng [E#] gắn
tại claim đó; nguồn chỉ liên quan chủ đề nhưng không chứa căn cứ cho claim vẫn là
không được hỗ trợ. Không coi suy luận hợp lý, kiến thức sẵn có hoặc câu trả lời cũ
là bằng chứng.

Trả status=need_more_search nếu có claim không được nguồn trích dẫn hỗ trợ, câu
trả lời bỏ sót ý chính, hoặc bằng chứng còn mâu thuẫn/thiếu. Mỗi claim chuyên môn
đã được gắn mã [C#] bên dưới. Với claim không được hỗ trợ, trả đúng số của mã đó
vào unsupported_claim_ids và sao chép nguyên văn câu vào unsupported_claims.
Không tự tạo mã, không tóm tắt, diễn giải hoặc chỉ chép một phần. Trả tối đa 4
claim và tối đa 4 câu hỏi tìm kiếm cụ thể trong missing_evidence. Chỉ trả
status=sufficient khi mọi claim chuyên môn
đều được nguồn tương ứng hỗ trợ. Không yêu cầu tìm thêm chỉ vì cách viết có thể
cải thiện. Không bắt mô tả quan sát trực tiếp từ ảnh, câu hỏi làm rõ, cảnh báo về
độ không chắc chắn hoặc dữ liệu hồ sơ người dùng phải có nguồn RAG.

Câu hỏi: {state['question']}
Câu trả lời đã sinh: {state.get('draft_answer')}
Các claim chuyên môn đã đánh số:
{numbered_claims_summary}
Trạng thái nghiên cứu: {research_summary}
Tài liệu đã dùng:
{docs_summary}"""
    try:
        decision = await _call_gemini(prompt)
    except ValidationError:
        logger.warning("Reflection returned invalid structured output; requesting more evidence")
        decision = ReflectionDecision(status="need_more_search")

    unsupported_claims = [
        " ".join(str(claim).split()).strip()
        for claim in decision.unsupported_claims
        if str(claim).strip()
    ][:4]
    unsupported_claim_ids = list(dict.fromkeys(
        claim_id
        for claim_id in decision.unsupported_claim_ids
        if isinstance(claim_id, int)
        and not isinstance(claim_id, bool)
        and 1 <= claim_id <= len(numbered_claims)
    ))[:4]
    if unsupported_claim_ids:
        unsupported_claims = [
            numbered_claims[claim_id - 1]
            for claim_id in unsupported_claim_ids
        ]
    if unsupported_claims or unsupported_claim_ids:
        context["claim_entailment_failed"] = True
        context["unsupported_claim_count"] = (
            len(unsupported_claim_ids) or len(unsupported_claims)
        )
        context["unsupported_claims"] = unsupported_claims
        context["unsupported_claim_ids"] = unsupported_claim_ids

        if (
            context.get("require_citation", False)
            and context.get("entailment_repair_attempted", False)
            and not context.get("unsupported_claim_prune_attempted", False)
            and not is_prune_recheck
        ):
            if unsupported_claim_ids:
                pruned, removed = prune_rejected_claim_ids(
                    state.get("draft_answer"), unsupported_claim_ids
                )
                expected_removed = len(unsupported_claim_ids)
            else:
                pruned, removed = prune_exact_rejected_claims(
                    state.get("draft_answer"), unsupported_claims
                )
                expected_removed = len(unsupported_claims)
            context["unsupported_claim_prune_attempted"] = True
            context["unsupported_claim_prune_count"] = len(removed)
            if (
                len(removed) == expected_removed
                and pruned
                and referenced_evidence_indexes(pruned)
            ):
                state["draft_answer"] = pruned
                used_ids = {
                    f"E{index}" for index in referenced_evidence_indexes(pruned)
                }
                state["citations"] = [
                    citation
                    for citation in state.get("citations", [])
                    if citation.get("citation_id") in used_ids
                ]
                context["reflection_recheck_required"] = True

    reflection_status = (
        "need_more_search"
        if unsupported_claims or unsupported_claim_ids
        else decision.status
    )
    state["reflection_notes"] = reflection_status
    if reflection_status == "need_more_search":
        state["missing_evidence"] = _bounded_missing_evidence(
            state, decision.missing_evidence
        )
        # Retrieval retries happen before generation in research_analysis.
        # Starting a second generation after low/medium-risk tokens have been
        # streamed would violate the canonical SSE contract.
        state["research_stop_reason"] = "answer_insufficient"
    elif context.get("entailment_repair_attempted", False):
        # The only route back into reflection after generation is the bounded
        # buffered entailment repair. Once the repaired answer is sufficient,
        # discard diagnostics that belonged to the rejected draft so they do
        # not make a valid response look incomplete to clients or evaluators.
        state["missing_evidence"] = []
        state["research_stop_reason"] = "sufficient"
    return state
