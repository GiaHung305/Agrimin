import re

from app.retrieval.evidence import is_traceable_active_evidence
from app.retrieval.source_authority import supports_high_risk, supports_numeric_dosage
from app.workflow.state import AgentState
from app.workflow.confidence import compute_confidence, RELEVANT_DOCUMENT_THRESHOLD

# Ngưỡng này cần tinh chỉnh sau bằng Golden Dataset (Sprint 6.3).
RELEVANCE_THRESHOLD = RELEVANT_DOCUMENT_THRESHOLD

_DOSAGE_PATTERN = re.compile(
    r"(?<!\w)(\d+(?:[.,]\d+)?)\s*(ml|l|mg|g|kg|ppm|%)(?!\w)",
    re.IGNORECASE,
)
_CITATION_MARKER_PATTERN = re.compile(r"\[E(\d+)\]", re.IGNORECASE)


def _dosage_claims(text: str | None) -> set[tuple[str, str]]:
    claims: set[tuple[str, str]] = set()
    for value, unit in _DOSAGE_PATTERN.findall(text or ""):
        normalized_value = value.replace(",", ".").lstrip("0") or "0"
        claims.add((normalized_value, unit.lower()))
    return claims


def _has_supported_dosage(state: AgentState) -> bool:
    answer_claims = _dosage_claims(state.get("draft_answer"))
    if not answer_claims:
        return True

    supported_claims: set[tuple[str, str]] = set()
    for evidence in state.get("retrieved_docs", []):
        if not is_traceable_active_evidence(evidence):
            continue
        if not supports_numeric_dosage(evidence.get("source_type")):
            continue
        if float(evidence.get("rerank_score") or 0) < RELEVANCE_THRESHOLD:
            continue
        supported_claims.update(_dosage_claims(evidence.get("content")))
    return answer_claims.issubset(supported_claims)


def _claim_citations_are_valid(state: AgentState, require_citation: bool) -> bool:
    markers = {
        int(value)
        for value in _CITATION_MARKER_PATTERN.findall(state.get("draft_answer") or "")
    }
    valid_markers = set(range(1, len(state.get("retrieved_docs", [])) + 1))
    if markers - valid_markers:
        state["context"]["guardrail_reason"] = "invalid_claim_citation"
        return False
    if require_citation and not markers:
        state["context"]["guardrail_reason"] = "missing_claim_citation"
        return False
    return True


async def post_guardrail_node(state: AgentState) -> AgentState:
    require_citation = state["context"].get("require_citation", False)
    max_relevance = state["context"].get("max_relevance_score", 0)
    relevant_docs = [
        doc
        for doc in state.get("retrieved_docs", [])
        if is_traceable_active_evidence(doc)
        and float(doc.get("rerank_score") or 0) >= RELEVANCE_THRESHOLD
    ]
    authoritative_docs = [
        doc for doc in relevant_docs if supports_high_risk(doc.get("source_type"))
    ]
    has_relevant_source = max_relevance >= RELEVANCE_THRESHOLD and bool(
        authoritative_docs if require_citation else relevant_docs
    )
    has_web_source = False

    if require_citation and not (has_relevant_source or has_web_source):
        state["confidence"] = 0.0
        state["guardrail_status"] = "block"
        return state

    if state.get("risk_level") == "high" and not _has_supported_dosage(state):
        state["confidence"] = 0.0
        state["guardrail_status"] = "block"
        state["context"]["guardrail_reason"] = "unsupported_numeric_dosage"
        return state

    if not _claim_citations_are_valid(state, require_citation):
        state["confidence"] = 0.0
        state["guardrail_status"] = "block"
        return state

    state["confidence"] = compute_confidence(
        rerank_scores=state["context"].get("rerank_scores", []),
        reflection_notes=state.get("reflection_notes"),
        retry_count=state.get("retry_count", 0),
        weather_requested=state.get("plan", {}).get("need_weather", False),
        weather_available="weather" in state.get("tool_results", {}),
        research_source_count=state["context"].get("research_source_count", 0),
    )

    if state["confidence"] < 0.70:
        state["draft_answer"] += "\n\n(Lưu ý: tôi chưa hoàn toàn chắc chắn, bạn nên hỏi thêm cán bộ khuyến nông.)"

    state["guardrail_status"] = "pass"
    return state
