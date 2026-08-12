import pytest

from app.workflow.nodes.fallback import fallback_node


@pytest.mark.asyncio
async def test_visual_fallback_is_specific_and_clears_rejected_citations():
    state = {
        "visual_observations": [{"relevance": "agriculture_plant"}],
        "context": {"guardrail_reason": "missing_claim_citation"},
        "citations": [{"citation_id": "E1"}],
        "retry_count": 0,
    }

    result = await fallback_node(state)

    assert result["citations"] == []
    assert "không kết luận bệnh chỉ từ ảnh" in result["final_answer"]
    assert "liều lượng" not in result["final_answer"]
