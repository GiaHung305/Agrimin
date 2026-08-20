"""Deterministic evidence coverage and contradiction analysis."""

from __future__ import annotations

import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import settings
from app.retrieval.evidence import evidence_identity, is_traceable_active_evidence
from app.retrieval.source_authority import supports_high_risk
from app.workflow.confidence import RELEVANT_DOCUMENT_THRESHOLD
from app.workflow.measurements import extract_numeric_measurements
from app.workflow.state import AgentState, EvidenceConflict, ResearchCoverageItem

MAX_RESEARCH_RETRIES = 2
_TIME_SENSITIVE_QUESTION_PHRASES = (
    "hien nay",
    "moi nhat",
    "nam nay",
    "gan day",
    "hom nay",
    "quy dinh",
    "danh muc thuoc",
    "du bao",
    "thoi tiet",
)


def _fold_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    without_marks = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )
    return " ".join(without_marks.replace("đ", "d").split())


def question_requires_fresh_evidence(question: str) -> bool:
    folded = _fold_text(question)
    return any(
        phrase in folded for phrase in _TIME_SENSITIVE_QUESTION_PHRASES
    )


def _published_datetime(document: dict[str, Any]) -> datetime | None:
    value = document.get("published_date")
    if isinstance(value, datetime):
        parsed = value
    elif value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def assess_freshness(
    question: str,
    documents: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> tuple[str, str | None]:
    dates = [
        published
        for document in documents
        if supports_high_risk(document.get("source_type"))
        and (published := _published_datetime(document)) is not None
    ]
    latest = max(dates, default=None)
    latest_iso = latest.isoformat() if latest else None
    if not question_requires_fresh_evidence(question):
        return "not_required", latest_iso
    if latest is None:
        return "unknown", None
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    cutoff = current_time.astimezone(timezone.utc) - timedelta(
        days=settings.research_freshness_max_age_days
    )
    return ("current" if latest >= cutoff else "stale"), latest_iso


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
        and supports_research_coverage(document)
    ]


def supports_research_coverage(document: dict[str, Any]) -> bool:
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
        freshness, latest_published_date = assess_freshness(question, relevant)
        coverage.append({
            "question": question,
            "covered": (
                bool(relevant)
                and (authoritative or not require_authority)
                and freshness not in {"stale", "unknown"}
            ),
            "best_score": max(
                (float(document.get("rerank_score") or 0.0) for document in relevant),
                default=0.0,
            ),
            "authoritative": authoritative,
            "freshness": freshness,
            "latest_published_date": latest_published_date,
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
            for value, unit in extract_numeric_measurements(
                str(document.get("content") or "")
            ):
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


def research_retry_limit(state: AgentState) -> int:
    """Spend retries only where additional evidence materially affects safety.

    Ordinary low-risk chat degrades with uncertainty after one retrieval pass.
    Vision gets one expanded pass; high-risk and explicit Deep Research retain
    the full bounded budget.
    """
    plan = state.get("plan") or {}
    if state.get("risk_level") == "high" or plan.get("need_deep_research", False):
        return MAX_RESEARCH_RETRIES
    if state.get("visual_observations"):
        return 1
    return 0


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
    elif state.get("retry_count", 0) < research_retry_limit(state):
        state["retry_count"] = state.get("retry_count", 0) + 1
        state["research_stop_reason"] = (
            "retry_contradiction" if conflicts else "retry_missing_evidence"
        )
    else:
        state["research_stop_reason"] = (
            "retry_limit_contradiction" if conflicts else "retry_limit_missing_evidence"
        )
    return state
