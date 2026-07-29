import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.workflow.nodes.post_guardrail import post_guardrail_node, RELEVANCE_THRESHOLD


def make_fake_state(risk_level="low", require_citation=False, max_relevance_score=0.5, confidence=0.8):
    return {
        "risk_level": risk_level,
        "context": {
            "require_citation": require_citation,
            "max_relevance_score": max_relevance_score,
        },
        "confidence": confidence,
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
    state = make_fake_state(risk_level="high", require_citation=True, max_relevance_score=0.01)
    result = await post_guardrail_node(state)
    assert result["guardrail_status"] == "block"


@pytest.mark.asyncio
async def test_guardrail_passes_high_risk_high_relevance():
    """Risk cao, cần citation, relevance score đủ cao (vượt ngưỡng) -> phải pass."""
    state = make_fake_state(risk_level="high", require_citation=True, max_relevance_score=RELEVANCE_THRESHOLD + 0.1)
    result = await post_guardrail_node(state)
    assert result["guardrail_status"] == "pass"


@pytest.mark.asyncio
async def test_guardrail_adds_disclaimer_low_confidence():
    """Confidence thấp -> phải thêm disclaimer vào câu trả lời."""
    state = make_fake_state(confidence=0.5)
    result = await post_guardrail_node(state)
    assert "chưa hoàn toàn chắc chắn" in result["draft_answer"]