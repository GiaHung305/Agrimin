from typing import Literal, Optional, TypedDict


class ResearchCoverageItem(TypedDict):
    question: str
    covered: bool
    best_score: float
    authoritative: bool
    evidence_ids: list[str]


class EvidenceConflict(TypedDict):
    kind: Literal["numeric_value_conflict"]
    question: str
    unit: str
    values: list[str]
    evidence_ids: list[str]


class AgentState(TypedDict):
    user_id: str
    conversation_id: str
    question: str
    image_observations: list[dict]
    visual_observations: list[dict]
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
    research_questions: list[str]
    research_coverage: list[ResearchCoverageItem]
    missing_evidence: list[str]
    evidence_conflicts: list[EvidenceConflict]
    research_stop_reason: Optional[str]
    guardrail_status: Optional[Literal["pass", "block"]]
    final_answer: Optional[str]
    research_sources: list
