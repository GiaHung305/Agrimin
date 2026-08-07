import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.workflow import graph as graph_module
from app.workflow.graph import (
    route_after_reflection,
    route_after_research_analysis,
)
from app.workflow.nodes import planner, retrieve
from app.workflow.nodes.research_analysis import (
    MAX_RESEARCH_RETRIES,
    assess_coverage,
    detect_numeric_conflicts,
    research_analysis_node,
)


def _evidence(
    document_id: str,
    question: str,
    content: str,
    *,
    score: float = 0.85,
    source_type: str = "government",
) -> dict:
    return {
        "document_id": document_id,
        "chunk_id": f"{document_id}-chunk",
        "is_active": True,
        "source": f"Nguồn {document_id}",
        "source_type": source_type,
        "content": content,
        "rerank_score": score,
        "research_questions": [question],
    }


def _research_state(*, risk_level: str = "low") -> dict:
    question = "Điều kiện đất và tưới phù hợp cho cà chua là gì?"
    return {
        "question": question,
        "plan": {"need_rag": True},
        "risk_level": risk_level,
        "research_questions": [question],
        "research_coverage": [],
        "missing_evidence": [],
        "evidence_conflicts": [],
        "research_stop_reason": None,
        "retry_count": 0,
        "retrieved_docs": [],
        "context": {},
    }


@pytest.mark.asyncio
async def test_planner_keeps_bounded_unique_research_questions(monkeypatch):
    async def decide(prompt):
        return planner.PlannerDecision(
            need_rag=True,
            need_weather=False,
            need_deep_research=False,
            risk_level="low",
            research_questions=[
                "  Nhu cầu đất?  ",
                "Nhu cầu tưới?",
                "Nhu cầu tưới?",
                "Bệnh thường gặp?",
            ],
        )

    monkeypatch.setattr(planner, "_call_gemini", decide)
    state = {"question": "Trồng cà chua thế nào?", "context": {}}
    result = await planner.planner_node(state)

    assert result["research_questions"] == [
        "Nhu cầu đất?",
        "Nhu cầu tưới?",
        "Bệnh thường gặp?",
    ]
    assert result["plan"]["research_questions"] == result["research_questions"]


@pytest.mark.asyncio
async def test_retrieve_runs_subquestions_and_merges_duplicate_evidence(monkeypatch):
    questions = ["Nhu cầu đất?", "Nhu cầu tưới?"]

    async def search(question, top_k):
        return [_evidence("doc-1", question, "Đất thoát nước và tưới vừa đủ.")]

    monkeypatch.setattr(retrieve, "hybrid_search", search)
    state = {
        "question": "Trồng cà chua thế nào?",
        "plan": {"need_rag": True, "need_weather": False},
        "research_questions": questions,
        "missing_evidence": [],
        "retry_count": 0,
        "retrieved_docs": [],
        "tool_results": {},
        "context": {},
    }

    result = await retrieve.retrieve_node(state)

    assert len(result["retrieved_docs"]) == 1
    assert result["retrieved_docs"][0]["research_questions"] == questions
    assert set(result["context"]["research_query_scores"]) == set(questions)


@pytest.mark.asyncio
async def test_retrieve_fuses_typed_visual_terms_into_first_query(monkeypatch):
    calls = []

    async def search(question, top_k):
        calls.append(question)
        return [_evidence("doc-vision", question, "Triệu chứng trên lá cà chua.")]

    monkeypatch.setattr(retrieve, "hybrid_search", search)
    base_question = "Lá này bị gì?"
    state = {
        "question": base_question,
        "plan": {"need_rag": True, "need_weather": False},
        "research_questions": [base_question],
        "missing_evidence": [],
        "retry_count": 0,
        "retrieved_docs": [],
        "tool_results": {},
        "visual_observations": [{
            "image_id": "0123456789abcdef",
            "relevance": "agriculture_plant",
            "crop_candidate": "cà chua",
            "plant_part": "leaf",
            "visible_symptoms": [],
            "limitations": ["single_view"],
            "confidence": 0.9,
        }],
        "context": {},
    }
    result = await retrieve.retrieve_node(state)
    assert "cà chua" in calls[0]
    assert "lá" in calls[0]
    assert result["context"]["vision_retrieval_query"] == calls[0]
    assert base_question in result["retrieved_docs"][0]["research_questions"]


def test_coverage_requires_authority_for_high_risk_research():
    state = _research_state(risk_level="high")
    question = state["research_questions"][0]
    state["retrieved_docs"] = [
        _evidence(
            "doc-1",
            question,
            "Pha theo hướng dẫn.",
            source_type="unknown",
        )
    ]

    coverage = assess_coverage(state)

    assert coverage[0]["best_score"] == 0.85
    assert coverage[0]["authoritative"] is False
    assert coverage[0]["covered"] is False


def test_coverage_accepts_dense_sparse_consensus_when_reranker_is_uncertain():
    state = _research_state()
    question = state["research_questions"][0]
    document = _evidence(
        "doc-1", question, "Đất cần thoát nước.", score=0.02
    )
    document.update({
        "ranking_strategy": "fusion_low_rerank_confidence",
        "dense_score": 0.71,
        "bm25_score": 4.2,
    })
    state["retrieved_docs"] = [document]

    assert assess_coverage(state)[0]["covered"] is True


def test_coverage_rejects_single_channel_low_confidence_candidate():
    state = _research_state()
    question = state["research_questions"][0]
    document = _evidence(
        "doc-1", question, "Tài liệu chỉ khớp dense.", score=0.02
    )
    document.update({
        "ranking_strategy": "fusion_low_rerank_confidence",
        "dense_score": 0.71,
        "bm25_score": None,
    })
    state["retrieved_docs"] = [document]

    assert assess_coverage(state)[0]["covered"] is False


@pytest.mark.asyncio
async def test_missing_evidence_retries_exactly_twice_then_stops():
    state = _research_state()

    for expected_retry in range(1, MAX_RESEARCH_RETRIES + 1):
        state = await research_analysis_node(state)
        assert state["retry_count"] == expected_retry
        assert state["research_stop_reason"] == "retry_missing_evidence"
        assert route_after_research_analysis(state) == "retrieve"

    state = await research_analysis_node(state)
    assert state["retry_count"] == MAX_RESEARCH_RETRIES
    assert state["research_stop_reason"] == "retry_limit_missing_evidence"
    assert route_after_research_analysis(state) == "generate"


def test_numeric_conflict_is_reported_across_independent_documents():
    state = _research_state()
    question = state["research_questions"][0]
    state["retrieved_docs"] = [
        _evidence("doc-1", question, "Khuyến cáo dùng 20 ml cho bình."),
        _evidence("doc-2", question, "Khuyến cáo dùng 30 ml cho bình."),
    ]

    conflicts = detect_numeric_conflicts(state)

    assert conflicts == [{
        "kind": "numeric_value_conflict",
        "question": question,
        "unit": "ml",
        "values": ["20", "30"],
        "evidence_ids": ["doc-1:doc-1-chunk", "doc-2:doc-2-chunk"],
    }]


def test_reflection_never_starts_a_second_streamed_generation():
    insufficient = {
        "reflection_notes": "need_more_search",
        "research_stop_reason": "answer_insufficient",
    }

    assert route_after_reflection(insufficient) == "post_guardrail"


@pytest.mark.asyncio
async def test_graph_exhausts_two_retrieval_retries_before_single_generation(
    monkeypatch,
):
    async def fake_planner(state):
        state.update({
            "plan": {"need_rag": True, "need_deep_research": False},
            "risk_level": "low",
            "research_questions": [state["question"]],
            "research_coverage": [],
            "missing_evidence": [],
            "evidence_conflicts": [],
            "research_stop_reason": None,
            "retry_count": 0,
        })
        return state

    async def passthrough(state, **kwargs):
        return state

    async def fake_retrieve(state):
        state["context"]["retrieve_calls"] = (
            state["context"].get("retrieve_calls", 0) + 1
        )
        state["retrieved_docs"] = []
        return state

    async def fake_generate(state):
        state["context"]["generation_calls"] = (
            state["context"].get("generation_calls", 0) + 1
        )
        state["draft_answer"] = "Chưa đủ bằng chứng."
        return state

    async def fake_reflection(state):
        state["reflection_notes"] = "need_more_search"
        state["research_stop_reason"] = "answer_insufficient"
        return state

    async def fake_post_guardrail(state):
        state["guardrail_status"] = "pass"
        state["final_answer"] = state["draft_answer"]
        return state

    monkeypatch.setattr(graph_module, "planner_node", fake_planner)
    monkeypatch.setattr(graph_module, "pre_guardrail_node", passthrough)
    monkeypatch.setattr(graph_module, "retrieve_node", fake_retrieve)
    monkeypatch.setattr(
        graph_module, "research_analysis_node", research_analysis_node
    )
    monkeypatch.setattr(graph_module, "generate_node", fake_generate)
    monkeypatch.setattr(graph_module, "reflection_node", fake_reflection)
    monkeypatch.setattr(graph_module, "post_guardrail_node", fake_post_guardrail)
    monkeypatch.setattr(graph_module, "memory_write_node", passthrough)
    monkeypatch.setattr(graph_module, "action_proposal_node", passthrough)
    monkeypatch.setattr(graph_module, "memory_extract_node", passthrough)
    monkeypatch.setattr(graph_module, "get_checkpointer", lambda: None)

    workflow = graph_module.build_graph(db=None)
    result = await workflow.ainvoke({
        "user_id": "user-1",
        "conversation_id": "conversation-1",
        "question": "Một câu hỏi chưa có tài liệu",
        "context": {},
        "pending_action": None,
        "plan": None,
        "risk_level": "low",
        "retrieved_docs": [],
        "tool_results": {},
        "draft_answer": None,
        "citations": [],
        "confidence": 0.0,
        "reflection_notes": None,
        "retry_count": 0,
        "research_questions": [],
        "research_coverage": [],
        "missing_evidence": [],
        "evidence_conflicts": [],
        "research_stop_reason": None,
        "guardrail_status": None,
        "final_answer": None,
        "research_sources": [],
    })

    assert result["retry_count"] == MAX_RESEARCH_RETRIES
    assert result["context"]["retrieve_calls"] == 3
    assert result["context"]["generation_calls"] == 1
