import unicodedata

from app.workflow.state import AgentState


_INTERPRETIVE_IMAGE_PHRASES = (
    "bi gi",
    "nguyen nhan",
    "do dau",
    "gia thuyet",
    "doi chieu",
    "co the la",
    "xu ly",
    "khac phuc",
    "nen lam",
    "thuoc gi",
    "phun gi",
    "bon gi",
)

_MISSING_SAFETY_CONTEXT_PHRASES = (
    "khong can biet ten thuoc",
    "khong can biet hoat chat",
    "khong biet ten thuoc",
    "khong biet hoat chat",
    "khong co nhan san pham",
    "khong can biet cay gi",
    "khong biet cay gi",
    "khong can biet tuoi cay",
    "khong can ket qua phan tich dat",
)

_ACTIONABLE_DOSAGE_PHRASES = (
    "bao nhieu",
    "lieu",
    "so ml",
    "so kg",
    "pha vao",
    "pha chung",
    "tron thuoc",
    "phun",
    "bon cho",
    "moi sao",
)


def _normalized_text(value: str) -> str:
    normalized = "".join(
        char
        for char in unicodedata.normalize("NFD", value.casefold())
        if unicodedata.category(char) != "Mn"
    ).replace("đ", "d")
    return " ".join(normalized.split())


def visual_answer_requires_citation(state: AgentState) -> bool:
    """Require evidence for interpretation, not direct visible description."""
    observations = state.get("visual_observations", [])
    if not observations:
        return False
    question = _normalized_text(state.get("question", ""))
    question = question.replace("khong chan doan", "")
    return any(phrase in question for phrase in _INTERPRETIVE_IMAGE_PHRASES)


def explicit_underspecified_dosage_request(question: str) -> bool:
    """Detect explicit unsafe dosage shortcuts without a model call."""
    normalized_question = _normalized_text(question)
    missing_context = any(
        phrase in normalized_question
        for phrase in _MISSING_SAFETY_CONTEXT_PHRASES
    )
    requests_actionable_dosage = any(
        phrase in normalized_question for phrase in _ACTIONABLE_DOSAGE_PHRASES
    )
    return missing_context and requests_actionable_dosage


def must_abstain_before_retrieval(state: AgentState) -> bool:
    """Reject explicitly under-specified dosage requests without model/tool calls.

    A product label/active ingredient or crop/soil context can materially change a
    safe dosage. When the user explicitly asks AgriMind to ignore that context,
    retrieval cannot make the request well-posed and repeated provider calls only
    add latency before the same required abstention.
    """
    return explicit_underspecified_dosage_request(state.get("question", ""))


async def pre_guardrail_node(state: AgentState) -> AgentState:
    """Set claim-level evidence requirements before retrieval/generation."""
    plan = state.get("plan") or {}
    requires_internal_rag_citation = bool(
        plan.get("need_rag", False)
        and not plan.get("need_deep_research", False)
    )
    state["context"]["require_citation"] = bool(
        state["risk_level"] == "high"
        or requires_internal_rag_citation
        or visual_answer_requires_citation(state)
    )
    if must_abstain_before_retrieval(state):
        state["risk_level"] = "high"
        state["context"]["pre_guardrail_stop"] = True
        state["context"]["guardrail_reason"] = "missing_safety_context"
        state["research_stop_reason"] = "pre_guardrail_abstain"
        state["guardrail_status"] = "block"
        state["confidence"] = 0.0
    else:
        state["context"].pop("pre_guardrail_stop", None)
        if state["context"].get("guardrail_reason") == "missing_safety_context":
            state["context"].pop("guardrail_reason", None)
    return state
