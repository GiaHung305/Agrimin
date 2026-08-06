from typing import TypedDict, Optional, Literal


class AgentState(TypedDict):
    user_id: str
    conversation_id: str
    question: str
    context: dict
    pending_action: Optional[dict]
    plan: Optional[dict]
    risk_level: Literal["low", "medium", "high"]
    retrieved_docs: list
    tool_results: dict
    draft_answer: Optional[str]
    citations: list
    confidence: float
    reflection_notes: Optional[str]
    retry_count: int
    guardrail_status: Optional[Literal["pass", "block"]]
    final_answer: Optional[str]
