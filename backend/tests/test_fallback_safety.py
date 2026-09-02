import pytest

from app.workflow.nodes.fallback import fallback_node


@pytest.mark.asyncio
async def test_visual_fallback_is_specific_and_clears_rejected_citations():
    state = {
        "visual_observations": [{"relevance": "agriculture_plant"}],
        "context": {"guardrail_reason": "missing_claim_citation"},
        "draft_answer": "Nội dung chẩn đoán bị từ chối [E1]",
        "citations": [{"citation_id": "E1"}],
        "answer_evidence": [{"content": "Bằng chứng cũ"}],
        "pending_action": {"kind": "unsafe"},
        "confidence": 0.9,
        "guardrail_status": "pass",
        "retry_count": 0,
    }

    result = await fallback_node(state)

    assert result["citations"] == []
    assert result["answer_evidence"] == []
    assert result["draft_answer"] is None
    assert result["pending_action"] is None
    assert result["confidence"] == 0.0
    assert result["guardrail_status"] == "block"
    assert result["context"]["user_response_kind"] == "abstention"
    assert "không kết luận bệnh chỉ từ ảnh" in result["final_answer"]
    assert "Nội dung chẩn đoán bị từ chối" not in result["final_answer"]
    assert "liều lượng" not in result["final_answer"]


@pytest.mark.asyncio
async def test_uncited_technical_claim_uses_source_specific_fallback():
    state = {
        "visual_observations": [],
        "context": {"guardrail_reason": "uncited_technical_claim"},
        "citations": [{"citation_id": "E1"}],
        "retry_count": 0,
    }

    result = await fallback_node(state)

    assert result["citations"] == []
    assert "chưa tìm được nguồn đủ phù hợp" in result["final_answer"]
    assert "liều lượng hoặc hóa chất" not in result["final_answer"]
    assert "truy vết" not in result["final_answer"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason",
    ["unsupported_claim_evidence", "insufficient_answer_evidence"],
)
async def test_reflection_failure_uses_source_specific_fallback(reason):
    state = {
        "visual_observations": [],
        "context": {"guardrail_reason": reason},
        "citations": [{"citation_id": "E1"}],
        "retry_count": 0,
    }

    result = await fallback_node(state)

    assert result["citations"] == []
    assert "chưa tìm được nguồn đủ phù hợp" in result["final_answer"]


@pytest.mark.asyncio
async def test_weather_failure_never_uses_chemical_fallback():
    state = {
        "visual_observations": [],
        "context": {"guardrail_reason": "missing_deterministic_weather_data"},
        "draft_answer": "Ngày mai chắc chắn không mưa.",
        "citations": [],
        "answer_evidence": [],
        "retry_count": 0,
    }

    result = await fallback_node(state)

    assert "dữ liệu dự báo hợp lệ" in result["final_answer"]
    assert result["context"]["user_response_kind"] == "weather_unavailable"
    assert "tỉnh/thành" in result["final_answer"]
    assert "hóa chất" not in result["final_answer"]
    assert "Ngày mai chắc chắn không mưa" not in result["final_answer"]


@pytest.mark.asyncio
async def test_missing_safety_context_requests_label_instead_of_guessing():
    state = {
        "visual_observations": [],
        "context": {"guardrail_reason": "missing_safety_context"},
        "draft_answer": "Pha 99 ml cho bình 16 lít.",
        "citations": [],
        "answer_evidence": [],
        "retry_count": 0,
    }

    result = await fallback_node(state)

    assert "thông tin quyết định liều" in result["final_answer"]
    assert result["context"]["user_response_kind"] == "abstention"
    assert "tên sản phẩm hoặc hoạt chất" in result["final_answer"]
    assert "ảnh nhãn" in result["final_answer"]
    assert "99 ml" not in result["final_answer"]


@pytest.mark.asyncio
async def test_unverified_dosage_requests_official_label_without_echoing_draft():
    state = {
        "visual_observations": [],
        "context": {"guardrail_reason": "unsupported_numeric_dosage"},
        "draft_answer": "Dùng 2 kg/ha và pha tỷ lệ 1:100.",
        "citations": [{"citation_id": "E1"}],
        "answer_evidence": [{"content": "Nguồn không hỗ trợ con số"}],
        "retry_count": 2,
    }

    result = await fallback_node(state)

    assert "không đoán con số" in result["final_answer"]
    assert "ảnh nhãn rõ phần liều dùng" in result["final_answer"]
    assert "2 kg/ha" not in result["final_answer"]
    assert "1:100" not in result["final_answer"]


@pytest.mark.asyncio
async def test_unknown_block_reason_stays_generic():
    state = {
        "visual_observations": [],
        "context": {"guardrail_reason": "future_reason"},
        "draft_answer": "Nội dung bị chặn",
        "citations": [],
        "answer_evidence": [],
        "retry_count": 0,
    }

    result = await fallback_node(state)

    assert "chưa có đủ căn cứ đáng tin cậy" in result["final_answer"]
    assert "liều lượng" not in result["final_answer"]
    assert "hóa chất" not in result["final_answer"]
