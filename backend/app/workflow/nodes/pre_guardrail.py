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


async def pre_guardrail_node(state: AgentState) -> AgentState:
    """Set claim-level evidence requirements before retrieval/generation."""
    state["context"]["require_citation"] = bool(
        state["risk_level"] == "high" or visual_answer_requires_citation(state)
    )
    return state
