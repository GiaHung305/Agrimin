import re

from app.retrieval.evidence import is_traceable_active_evidence
from app.retrieval.source_authority import supports_high_risk, supports_numeric_dosage
from app.workflow.state import AgentState
from app.workflow.confidence import compute_confidence, RELEVANT_DOCUMENT_THRESHOLD
from app.workflow.measurements import extract_numeric_measurements
from app.workflow.nodes.research_analysis import supports_research_coverage

# Ngưỡng này cần tinh chỉnh sau bằng Golden Dataset (Sprint 6.3).
RELEVANCE_THRESHOLD = RELEVANT_DOCUMENT_THRESHOLD

_CITATION_MARKER_PATTERN = re.compile(r"\[E(\d+)\]", re.IGNORECASE)
_VISUAL_UNCERTAINTY_PATTERN = re.compile(
    r"\b(có thể|giả thuyết|chưa đủ|không (?:thể )?kết luận|"
    r"cần (?:thêm|bổ sung|quan sát))\b",
    re.IGNORECASE,
)


def _has_supported_dosage(
    state: AgentState, cited_documents: list[dict]
) -> bool:
    answer_claims = extract_numeric_measurements(state.get("draft_answer"))
    if not answer_claims:
        return True

    supported_claims: set[tuple[str, str]] = set()
    for evidence in cited_documents:
        if not is_traceable_active_evidence(evidence):
            continue
        if not supports_numeric_dosage(evidence.get("source_type")):
            continue
        if float(evidence.get("rerank_score") or 0) < RELEVANCE_THRESHOLD:
            continue
        supported_claims.update(
            extract_numeric_measurements(evidence.get("content"))
        )
    return answer_claims.issubset(supported_claims)


def _claim_citations_are_valid(
    state: AgentState, require_citation: bool
) -> tuple[bool, list[dict]]:
    markers = list(dict.fromkeys(
        int(value)
        for value in _CITATION_MARKER_PATTERN.findall(state.get("draft_answer") or "")
    ))
    documents = state.get("answer_evidence", state.get("retrieved_docs", []))
    valid_markers = set(range(1, len(documents) + 1))
    if set(markers) - valid_markers:
        state["context"]["guardrail_reason"] = "invalid_claim_citation"
        return False, []
    if require_citation and not markers:
        state["context"]["guardrail_reason"] = "missing_claim_citation"
        return False, []

    cited_documents = [documents[index - 1] for index in markers]
    for document in cited_documents:
        if not is_traceable_active_evidence(document):
            state["context"]["guardrail_reason"] = "untraceable_claim_citation"
            return False, []
        if state.get("risk_level") == "high":
            if (
                float(document.get("rerank_score") or 0) < RELEVANCE_THRESHOLD
                or not supports_high_risk(document.get("source_type"))
            ):
                state["context"]["guardrail_reason"] = (
                    "non_authoritative_claim_citation"
                )
                return False, []
        elif not supports_research_coverage(document):
            state["context"]["guardrail_reason"] = "irrelevant_claim_citation"
            return False, []
    return True, cited_documents


async def post_guardrail_node(state: AgentState) -> AgentState:
    require_citation = state["context"].get("require_citation", False)
    citations_valid, cited_documents = _claim_citations_are_valid(
        state, require_citation
    )
    if not citations_valid:
        state["confidence"] = 0.0
        state["guardrail_status"] = "block"
        return state

    if state.get("risk_level") == "high" and not _has_supported_dosage(
        state, cited_documents
    ):
        state["confidence"] = 0.0
        state["guardrail_status"] = "block"
        state["context"]["guardrail_reason"] = "unsupported_numeric_dosage"
        return state

    if (
        state.get("risk_level") == "low"
        and state.get("context", {}).get("deterministic_action_response")
    ):
        state["confidence"] = 1.0
        state["guardrail_status"] = "pass"
        return state

    if (
        state.get("visual_observations")
        and not _VISUAL_UNCERTAINTY_PATTERN.search(state.get("draft_answer") or "")
    ):
        state["draft_answer"] += (
            "\n\nẢnh chỉ hỗ trợ giả thuyết, chưa đủ để kết luận bệnh; cần thêm "
            "ảnh hai mặt lá và thông tin diễn biến ngoài ruộng."
        )

    state["confidence"] = compute_confidence(
        rerank_scores=[
            float(document.get("rerank_score") or 0.0)
            for document in cited_documents
        ] or state["context"].get("rerank_scores", []),
        reflection_notes=state.get("reflection_notes"),
        retry_count=state.get("retry_count", 0),
        weather_requested=state.get("plan", {}).get("need_weather", False),
        weather_available="weather" in state.get("tool_results", {}),
        research_source_count=state["context"].get("research_source_count", 0),
        visual_confidences=[
            float(item.get("confidence") or 0.0)
            for item in state.get("visual_observations", [])
        ],
    )

    if state["confidence"] < 0.70:
        state["draft_answer"] += (
            "\n\n(Lưu ý: mình chưa hoàn toàn chắc chắn; bạn nên kiểm tra thêm "
            "với cán bộ khuyến nông.)"
        )

    state["guardrail_status"] = "pass"
    return state
