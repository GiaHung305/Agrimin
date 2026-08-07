"""Deterministic evidence coverage and contradiction analysis."""

from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.config import settings
from app.retrieval.evidence import evidence_identity, is_traceable_active_evidence
from app.retrieval.source_authority import supports_high_risk
from app.workflow.confidence import RELEVANT_DOCUMENT_THRESHOLD
from app.workflow.state import AgentState, EvidenceConflict, ResearchCoverageItem

MAX_RESEARCH_RETRIES = 2
_NUMBER_WITH_UNIT = re.compile(
    r"(?<!\w)(\d+(?:[.,]\d+)?)\s*(ml|l|mg|g|kg|ppm|%)(?!\w)",
    re.IGNORECASE,
)


def _normalized_number(value: str) -> str:
    try:
        number = Decimal(value.replace(",", ".")).normalize()
    except InvalidOperation:
        return value
    return format(number, "f")


def _matches_question(document: dict[str, Any], question: str) -> bool:
    labels = document.get("research_questions", [])
    return not labels or question in labels


def _relevant_documents(
    documents: list[dict[str, Any]], question: str
) -> list[dict[str, Any]]:
    return [
        document
        for document in documents
        if _matches_question(document, question)
        and is_traceable_active_evidence(document)
        and _supports_research_coverage(document)
    ]


def _supports_research_coverage(document: dict[str, Any]) -> bool:
    """Accept calibrated reranking or explicit dense+sparse consensus.

    The cross-encoder can produce uniformly low probabilities for a query. In
    that case hybrid_search deliberately preserves weighted-RRF order, so using
    the high-risk reranker threshold here would trigger retries even when both
    retrievers found the same traceable chunk. This rule is only for research
    coverage; post_guardrail keeps its stricter high-risk threshold.
    """
    rerank_score = float(document.get("rerank_score") or 0.0)
    if rerank_score >= RELEVANT_DOCUMENT_THRESHOLD:
        return True
    strategy = document.get("ranking_strategy")
    if strategy == "rerank":
        return rerank_score >= settings.rerank_min_confidence
    if strategy == "fusion_low_rerank_confidence":
        return (
            float(document.get("dense_score") or 0.0) > 0.0
            and float(document.get("bm25_score") or 0.0) > 0.0
        )
    return False


def assess_coverage(state: AgentState) -> list[ResearchCoverageItem]:
    questions = state.get("research_questions", [])
    documents = state.get("retrieved_docs", [])
    require_authority = state.get("risk_level") == "high"
    coverage: list[ResearchCoverageItem] = []
    for question in questions:
        relevant = _relevant_documents(documents, question)
        authoritative = any(
            supports_high_risk(document.get("source_type")) for document in relevant
        )
        coverage.append({
            "question": question,
            "covered": bool(relevant) and (authoritative or not require_authority),
            "best_score": max(
                (float(document.get("rerank_score") or 0.0) for document in relevant),
                default=0.0,
            ),
            "authoritative": authoritative,
            "evidence_ids": [evidence_identity(document) for document in relevant],
        })
    return coverage


def detect_numeric_conflicts(state: AgentState) -> list[EvidenceConflict]:
    conflicts: list[EvidenceConflict] = []
    for question in state.get("research_questions", []):
        documents = _relevant_documents(state.get("retrieved_docs", []), question)
        claims: dict[str, dict[str, set[str]]] = defaultdict(
            lambda: defaultdict(set)
        )
        source_documents: dict[str, set[str]] = defaultdict(set)
        for document in documents:
            document_key = str(document.get("document_id") or evidence_identity(document))
            evidence_key = evidence_identity(document)
            for raw_value, raw_unit in _NUMBER_WITH_UNIT.findall(
                str(document.get("content") or "")
            ):
                unit = raw_unit.casefold()
                value = _normalized_number(raw_value)
                claims[unit][value].add(evidence_key)
                source_documents[unit].add(document_key)

        for unit, values in claims.items():
            if len(values) < 2 or len(source_documents[unit]) < 2:
                continue
            conflicts.append({
                "kind": "numeric_value_conflict",
                "question": question,
                "unit": unit,
                "values": sorted(values),
                "evidence_ids": sorted({
                    evidence_id
                    for evidence_ids in values.values()
                    for evidence_id in evidence_ids
                }),
            })
    return conflicts


def _unique_questions(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


async def research_analysis_node(state: AgentState) -> AgentState:
    plan = state.get("plan") or {}
    if not plan.get("need_rag", True):
        state["research_coverage"] = []
        state["missing_evidence"] = []
        state["evidence_conflicts"] = []
        state["research_stop_reason"] = "no_research_required"
        return state

    coverage = assess_coverage(state)
    conflicts = detect_numeric_conflicts(state)
    missing = [item["question"] for item in coverage if not item["covered"]]
    unresolved = _unique_questions([
        *missing,
        *(conflict["question"] for conflict in conflicts),
    ])

    state["research_coverage"] = coverage
    state["missing_evidence"] = unresolved
    state["evidence_conflicts"] = conflicts
    if not unresolved:
        state["research_stop_reason"] = "sufficient"
    elif state.get("retry_count", 0) < MAX_RESEARCH_RETRIES:
        state["retry_count"] = state.get("retry_count", 0) + 1
        state["research_stop_reason"] = (
            "retry_contradiction" if conflicts else "retry_missing_evidence"
        )
    else:
        state["research_stop_reason"] = (
            "retry_limit_contradiction" if conflicts else "retry_limit_missing_evidence"
        )
    return state
