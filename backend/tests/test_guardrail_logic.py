import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.workflow.confidence import compute_confidence
from app.workflow.nodes.post_guardrail import post_guardrail_node, RELEVANCE_THRESHOLD
from app.workflow.nodes.pre_guardrail import pre_guardrail_node


def make_fake_state(risk_level="low", require_citation=False, rerank_scores=None):
    rerank_scores = rerank_scores or [0.8]
    return {
        "risk_level": risk_level,
        "context": {
            "require_citation": require_citation,
            "max_relevance_score": max(rerank_scores),
            "rerank_scores": rerank_scores,
        },
        "plan": {"need_weather": False},
        "tool_results": {},
        "retrieved_docs": [{
            "document_id": "doc-1",
            "chunk_id": "chunk-1",
            "is_active": True,
            "source_type": "government",
            "content": "Tài liệu mẫu",
            "rerank_score": rerank_scores[0],
        }],
        "reflection_notes": "sufficient",
        "retry_count": 0,
        "draft_answer": "Câu trả lời mẫu",
    }


@pytest.mark.asyncio
async def test_guardrail_passes_low_risk():
    """Câu hỏi risk thấp, không cần citation bắt buộc -> phải pass."""
    state = make_fake_state(risk_level="low", require_citation=False)
    result = await post_guardrail_node(state)
    assert result["guardrail_status"] == "pass"


@pytest.mark.asyncio
async def test_guardrail_blocks_high_risk_low_relevance():
    """Risk cao, cần citation, nhưng relevance score thấp hơn ngưỡng -> phải block."""
    state = make_fake_state(risk_level="high", require_citation=True, rerank_scores=[0.01])
    result = await post_guardrail_node(state)
    assert result["guardrail_status"] == "block"


@pytest.mark.asyncio
async def test_guardrail_passes_high_risk_high_relevance():
    """Risk cao, cần citation, relevance score đủ cao (vượt ngưỡng) -> phải pass."""
    state = make_fake_state(risk_level="high", require_citation=True, rerank_scores=[RELEVANCE_THRESHOLD + 0.1])
    state["draft_answer"] += " [E1]"
    result = await post_guardrail_node(state)
    assert result["guardrail_status"] == "pass"


@pytest.mark.asyncio
async def test_guardrail_blocks_high_risk_unknown_source():
    state = make_fake_state(
        risk_level="high",
        require_citation=True,
        rerank_scores=[RELEVANCE_THRESHOLD + 0.1],
    )
    state["retrieved_docs"][0]["source_type"] = "unknown"
    result = await post_guardrail_node(state)
    assert result["guardrail_status"] == "block"


@pytest.mark.asyncio
async def test_guardrail_blocks_uncited_high_risk_dosage():
    state = make_fake_state(
        risk_level="high", require_citation=True, rerank_scores=[0.01]
    )
    state["draft_answer"] = "Pha 20 ml cho bình 16 l."
    result = await post_guardrail_node(state)
    assert result["guardrail_status"] == "block"


@pytest.mark.asyncio
async def test_guardrail_blocks_dosage_missing_from_relevant_chunk():
    state = make_fake_state(
        risk_level="high",
        require_citation=True,
        rerank_scores=[RELEVANCE_THRESHOLD + 0.1],
    )
    state["draft_answer"] = "Pha 20 ml cho bình 16 l."
    state["retrieved_docs"][0]["content"] = "Luôn đọc nhãn và mang đồ bảo hộ."
    result = await post_guardrail_node(state)
    assert result["guardrail_status"] == "block"
    assert result["context"]["guardrail_reason"] == "unsupported_numeric_dosage"


@pytest.mark.asyncio
async def test_guardrail_blocks_dosage_from_research_paper():
    state = make_fake_state(
        risk_level="high",
        require_citation=True,
        rerank_scores=[RELEVANCE_THRESHOLD + 0.1],
    )
    state["draft_answer"] = "Theo nghiên cứu, pha 20 ml cho bình 16 l."
    state["retrieved_docs"][0].update(
        {
            "source_type": "research",
            "content": "Nghiên cứu thử nghiệm pha 20 ml cho bình 16 l.",
        }
    )
    result = await post_guardrail_node(state)
    assert result["guardrail_status"] == "block"
    assert result["context"]["guardrail_reason"] == "unsupported_numeric_dosage"


@pytest.mark.asyncio
async def test_guardrail_passes_dosage_supported_by_traceable_chunk():
    state = make_fake_state(
        risk_level="high",
        require_citation=True,
        rerank_scores=[RELEVANCE_THRESHOLD + 0.1],
    )
    state["draft_answer"] = "Theo nhãn, pha 20 ml cho bình 16 l. [E1]"
    state["retrieved_docs"][0]["content"] = "Hướng dẫn trên nhãn: pha 20 ml cho bình 16 l."
    result = await post_guardrail_node(state)
    assert result["guardrail_status"] == "pass"


@pytest.mark.asyncio
async def test_guardrail_blocks_high_risk_answer_without_claim_marker():
    state = make_fake_state(
        risk_level="high",
        require_citation=True,
        rerank_scores=[RELEVANCE_THRESHOLD + 0.1],
    )
    result = await post_guardrail_node(state)
    assert result["guardrail_status"] == "block"
    assert result["context"]["guardrail_reason"] == "missing_claim_citation"


@pytest.mark.asyncio
async def test_guardrail_blocks_fabricated_claim_marker():
    state = make_fake_state(risk_level="low", require_citation=False)
    state["draft_answer"] = "Khẳng định không có nguồn [E99]"
    result = await post_guardrail_node(state)
    assert result["guardrail_status"] == "block"
    assert result["context"]["guardrail_reason"] == "invalid_claim_citation"


@pytest.mark.asyncio
async def test_guardrail_adds_disclaimer_low_confidence():
    """Confidence thấp -> phải thêm disclaimer vào câu trả lời."""
    state = make_fake_state(rerank_scores=[0.2])
    result = await post_guardrail_node(state)
    assert "chưa hoàn toàn chắc chắn" in result["draft_answer"]


def test_confidence_rewards_grounded_and_corroborated_answer():
    confidence = compute_confidence(
        rerank_scores=[0.92, 0.81, 0.72],
        reflection_notes="sufficient",
    )
    assert confidence >= 0.85


def test_confidence_penalizes_missing_or_insufficient_evidence():
    assert compute_confidence([], "sufficient") == 0.0
    confidence = compute_confidence(
        rerank_scores=[0.55],
        reflection_notes="need_more_search",
        retry_count=2,
        weather_requested=True,
        weather_available=False,
    )
    assert confidence < 0.20


def test_confidence_uses_grounded_research_sources_when_rag_is_empty():
    confidence = compute_confidence(
        rerank_scores=[],
        reflection_notes="sufficient",
        research_source_count=3,
    )
    assert confidence >= 0.70


@pytest.mark.asyncio
async def test_visual_observations_always_require_citations():
    state = make_fake_state(risk_level="low", require_citation=False)
    state["visual_observations"] = [{"relevance": "agriculture_plant"}]
    state = await pre_guardrail_node(state)
    assert state["context"]["require_citation"] is True
