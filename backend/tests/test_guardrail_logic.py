import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.workflow.confidence import (
    TRUSTED_ANSWER_CONFIDENCE_THRESHOLD,
    compute_confidence,
    compute_weather_response_confidence,
)
from app.workflow import graph
from app.workflow.nodes.post_guardrail import post_guardrail_node, RELEVANCE_THRESHOLD
from app.workflow.graph import route_after_early_guardrail, route_after_pre_guardrail
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
async def test_guardrail_trusts_valid_deterministic_action_reply():
    state = make_fake_state(risk_level="low", require_citation=False)
    state["context"]["deterministic_action_response"] = True
    state["retrieved_docs"] = []
    state["draft_answer"] = "Mình đã chuẩn bị lời nhắc để bạn xác nhận."

    result = await post_guardrail_node(state)

    assert result["guardrail_status"] == "pass"
    assert result["confidence"] == 1.0
    assert "khuyến nông" not in result["draft_answer"]


@pytest.mark.asyncio
async def test_guardrail_trusts_low_risk_deterministic_weather_status():
    state = make_fake_state(risk_level="low", require_citation=True)
    state["context"]["deterministic_safe_response"] = "weather_status"
    state["retrieved_docs"] = []
    state["draft_answer"] = "Bạn muốn xem thời tiết ở tỉnh nào?"

    result = await post_guardrail_node(state)

    assert result["guardrail_status"] == "pass"
    assert result["confidence"] == 1.0


@pytest.mark.asyncio
async def test_guardrail_weather_forecast_confidence_is_dynamic_not_absolute():
    state = make_fake_state(risk_level="low", require_citation=False)
    state["context"]["deterministic_safe_response"] = "weather_forecast"
    state["retrieved_docs"] = []
    state["tool_results"] = {
        "weather": {
            "from_cache": True,
            "forecast": [{
                "date": "2026-08-31",
                "temp_min": 22,
                "temp_max": 30,
                "humidity_max": 88,
                "description": "mưa nhẹ",
                "rain_probability": 0.6,
                "rain_mm": 4.2,
            }],
        }
    }
    state["draft_answer"] = "Dự báo đã được định dạng từ dữ liệu hợp lệ."

    result = await post_guardrail_node(state)

    assert result["guardrail_status"] == "pass"
    assert TRUSTED_ANSWER_CONFIDENCE_THRESHOLD <= result["confidence"] < 1.0


@pytest.mark.asyncio
async def test_guardrail_blocks_weather_forecast_marker_without_weather_data():
    state = make_fake_state(risk_level="low", require_citation=False)
    state["context"]["deterministic_safe_response"] = "weather_forecast"
    state["retrieved_docs"] = []
    state["tool_results"] = {}

    result = await post_guardrail_node(state)

    assert result["guardrail_status"] == "block"
    assert result["confidence"] == 0.0
    assert result["context"]["guardrail_reason"] == (
        "missing_deterministic_weather_data"
    )


@pytest.mark.asyncio
async def test_pre_guardrail_requires_citation_for_internal_rag():
    state = make_fake_state(risk_level="low", require_citation=False)
    state["question"] = "Cách tỉa cành cà chua?"
    state["plan"] = {
        "need_rag": True,
        "need_deep_research": False,
        "need_weather": False,
    }

    result = await pre_guardrail_node(state)

    assert result["context"]["require_citation"] is True


@pytest.mark.asyncio
async def test_pre_guardrail_keeps_non_rag_low_risk_chat_streamable():
    state = make_fake_state(risk_level="low", require_citation=False)
    state["question"] = "Xin chào"
    state["plan"] = {
        "need_rag": False,
        "need_deep_research": False,
        "need_weather": False,
    }

    result = await pre_guardrail_node(state)

    assert result["context"]["require_citation"] is False


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
    state["draft_answer"] += " [E1]"
    result = await post_guardrail_node(state)
    assert result["guardrail_status"] == "block"
    assert result["context"]["guardrail_reason"] == (
        "non_authoritative_claim_citation"
    )


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
    state["draft_answer"] = "Pha 20 ml cho bình 16 l. [E1]"
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
    state["draft_answer"] = "Theo nghiên cứu, pha 20 ml cho bình 16 l. [E1]"
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
async def test_guardrail_normalizes_cc_to_ml_against_authoritative_evidence():
    state = make_fake_state(
        risk_level="high",
        require_citation=True,
        rerank_scores=[RELEVANCE_THRESHOLD + 0.1],
    )
    state["draft_answer"] = "Theo nhãn, dùng 20 cc. [E1]"
    state["retrieved_docs"][0]["content"] = "Nhãn ghi lượng dùng 20 ml."

    result = await post_guardrail_node(state)

    assert result["guardrail_status"] == "pass"


@pytest.mark.asyncio
async def test_guardrail_blocks_unsupported_rate_or_dilution_ratio():
    state = make_fake_state(
        risk_level="high",
        require_citation=True,
        rerank_scores=[RELEVANCE_THRESHOLD + 0.1],
    )
    state["draft_answer"] = "Dùng 2 kg/ha và pha tỷ lệ 1:100. [E1]"
    state["retrieved_docs"][0]["content"] = (
        "Nhãn ghi 2 kg/ha và tỷ lệ 1:200."
    )

    result = await post_guardrail_node(state)

    assert result["guardrail_status"] == "block"
    assert result["context"]["guardrail_reason"] == "unsupported_numeric_dosage"


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
async def test_guardrail_blocks_an_uncited_technical_claim_in_grounded_answer():
    state = make_fake_state(
        risk_level="medium",
        require_citation=True,
        rerank_scores=[RELEVANCE_THRESHOLD + 0.1],
    )
    state["draft_answer"] = (
        "Thoát nước để hạn chế úng [E1]. "
        "Bón thêm đạm để cây phục hồi nhanh."
    )

    result = await post_guardrail_node(state)

    assert result["guardrail_status"] == "block"
    assert result["confidence"] == 0.0
    assert result["context"]["guardrail_reason"] == "uncited_technical_claim"
    assert result["context"]["uncited_claim_count"] == 1


@pytest.mark.asyncio
async def test_guardrail_accepts_each_technical_claim_with_a_local_marker():
    state = make_fake_state(
        risk_level="medium",
        require_citation=True,
        rerank_scores=[RELEVANCE_THRESHOLD + 0.1],
    )
    state["draft_answer"] = (
        "Thoát nước để hạn chế úng [E1]. "
        "Bón cân đối theo phân tích đất [E1]."
    )

    result = await post_guardrail_node(state)

    assert result["guardrail_status"] == "pass"


@pytest.mark.asyncio
async def test_guardrail_blocks_cited_claim_rejected_by_reflection():
    state = make_fake_state(
        risk_level="medium",
        require_citation=True,
        rerank_scores=[RELEVANCE_THRESHOLD + 0.1],
    )
    state["draft_answer"] = "Bón thêm đạm để cây phục hồi [E1]."
    state["reflection_notes"] = "need_more_search"
    state["context"]["claim_entailment_failed"] = True
    state["context"]["unsupported_claim_count"] = 1

    result = await post_guardrail_node(state)

    assert result["guardrail_status"] == "block"
    assert result["confidence"] == 0.0
    assert result["context"]["guardrail_reason"] == (
        "unsupported_claim_evidence"
    )


@pytest.mark.asyncio
async def test_guardrail_blocks_citation_required_answer_when_evidence_is_insufficient():
    state = make_fake_state(
        risk_level="medium",
        require_citation=True,
        rerank_scores=[RELEVANCE_THRESHOLD + 0.1],
    )
    state["draft_answer"] = "Thoát nước để hạn chế úng [E1]."
    state["reflection_notes"] = "need_more_search"

    result = await post_guardrail_node(state)

    assert result["guardrail_status"] == "block"
    assert result["context"]["guardrail_reason"] == (
        "insufficient_answer_evidence"
    )


@pytest.mark.asyncio
async def test_non_rag_chat_keeps_stream_compatible_low_confidence_behavior():
    state = make_fake_state(
        risk_level="low", require_citation=False, rerank_scores=[0.8]
    )
    state["reflection_notes"] = "need_more_search"

    result = await post_guardrail_node(state)

    assert result["guardrail_status"] == "pass"
    assert "chưa hoàn toàn chắc chắn" in result["draft_answer"]


@pytest.mark.asyncio
async def test_guardrail_adds_disclaimer_low_confidence():
    """Confidence thấp -> phải thêm disclaimer vào câu trả lời."""
    state = make_fake_state(rerank_scores=[0.2])
    result = await post_guardrail_node(state)
    assert "chưa hoàn toàn chắc chắn" in result["draft_answer"]


@pytest.mark.asyncio
async def test_guardrail_adds_missing_visual_uncertainty_limit():
    state = make_fake_state(require_citation=True)
    state["draft_answer"] = "Đối chiếu triệu chứng lá [E1]."
    state["visual_observations"] = [{"confidence": 0.9}]

    result = await post_guardrail_node(state)

    assert result["guardrail_status"] == "pass"
    assert "chưa đủ để kết luận bệnh" in result["draft_answer"]


def test_confidence_rewards_grounded_and_corroborated_answer():
    confidence = compute_confidence(
        rerank_scores=[0.92, 0.81, 0.72],
        reflection_notes="sufficient",
    )
    assert confidence >= 0.85


def test_weather_response_confidence_rewards_complete_fresh_short_forecast():
    complete = compute_weather_response_confidence([{
        "temp_min": 22,
        "temp_max": 30,
        "humidity_max": 88,
        "description": "mưa nhẹ",
        "rain_probability": 0.6,
        "rain_mm": 4.2,
    }])
    sparse_cached = compute_weather_response_confidence(
        [
            {"rain_probability": 0.2, "rain_mm": 0.0},
            {"rain_probability": 0.4, "rain_mm": 2.0},
            {"rain_probability": 0.3, "rain_mm": 1.0},
        ],
        from_cache=True,
    )

    assert complete == pytest.approx(0.92)
    assert sparse_cached == pytest.approx(0.73)
    assert sparse_cached < complete < 1.0


def test_confidence_does_not_treat_duplicate_chunks_as_independent_documents():
    duplicate_chunks = compute_confidence(
        rerank_scores=[0.92, 0.81, 0.72],
        reflection_notes="sufficient",
        independent_document_count=1,
    )
    independent_documents = compute_confidence(
        rerank_scores=[0.92, 0.81, 0.72],
        reflection_notes="sufficient",
        independent_document_count=3,
    )

    assert duplicate_chunks < independent_documents
    assert duplicate_chunks == pytest.approx(0.73)
    assert independent_documents >= 0.85


@pytest.mark.asyncio
async def test_guardrail_corroboration_counts_unique_document_ids():
    def state_with_documents(document_ids):
        state = make_fake_state(
            risk_level="low",
            require_citation=True,
            rerank_scores=[0.92, 0.81, 0.72],
        )
        state["retrieved_docs"] = [
            {
                "document_id": document_id,
                "chunk_id": f"chunk-{index}",
                "is_active": True,
                "source_type": "government",
                "content": f"Tài liệu hỗ trợ {index}",
                "rerank_score": score,
            }
            for index, (document_id, score) in enumerate(
                zip(document_ids, [0.92, 0.81, 0.72]),
                start=1,
            )
        ]
        state["draft_answer"] = "Các tài liệu cùng hỗ trợ kết luận [E1][E2][E3]."
        return state

    duplicate = await post_guardrail_node(
        state_with_documents(["doc-1", "doc-1", "doc-1"])
    )
    independent = await post_guardrail_node(
        state_with_documents(["doc-1", "doc-2", "doc-3"])
    )

    assert duplicate["guardrail_status"] == "pass"
    assert independent["guardrail_status"] == "pass"
    assert duplicate["context"]["independent_document_count"] == 1
    assert independent["context"]["independent_document_count"] == 3
    assert duplicate["confidence"] < independent["confidence"]


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


def test_web_only_grounding_stays_below_trusted_threshold():
    confidence = compute_confidence(
        rerank_scores=[],
        reflection_notes="sufficient",
        research_source_count=3,
    )
    assert confidence == pytest.approx(0.55)
    assert confidence < TRUSTED_ANSWER_CONFIDENCE_THRESHOLD


@pytest.mark.asyncio
async def test_low_risk_provider_grounding_is_valid_claim_evidence():
    state = make_fake_state(risk_level="low", require_citation=True)
    state["draft_answer"] = "Đất cần thoát nước tốt.[E1]"
    state["answer_evidence"] = [{
        "document_id": "https://example.gov/guide",
        "chunk_id": "grounding-1",
        "content": "Đất cần thoát nước tốt.",
        "source": "Nguồn web",
        "source_type": "unknown",
        "is_active": True,
        "ranking_strategy": "provider_grounding",
        "rerank_score": None,
    }]
    state["reflection_notes"] = "sufficient"
    state["context"]["research_source_count"] = 1
    state["context"]["research_independent_domain_count"] = 1

    result = await post_guardrail_node(state)

    assert result["guardrail_status"] == "pass"
    assert result["confidence"] == pytest.approx(0.35)
    assert "chưa hoàn toàn chắc chắn" in result["draft_answer"]


@pytest.mark.asyncio
async def test_high_risk_provider_grounding_is_not_authoritative_enough():
    state = make_fake_state(risk_level="high", require_citation=True)
    state["draft_answer"] = "Phun 20 ml thuốc.[E1]"
    state["answer_evidence"] = [{
        "document_id": "https://example.com/blog",
        "chunk_id": "grounding-1",
        "content": "Phun 20 ml thuốc.",
        "source": "Blog",
        "source_type": "unknown",
        "is_active": True,
        "ranking_strategy": "provider_grounding",
        "rerank_score": None,
    }]

    result = await post_guardrail_node(state)

    assert result["guardrail_status"] == "block"
    assert result["context"]["guardrail_reason"] == (
        "non_authoritative_claim_citation"
    )


def test_confidence_uses_trusted_farm_context_for_direct_saved_facts():
    confidence = compute_confidence(
        rerank_scores=[],
        reflection_notes="sufficient",
        trusted_context_count=1,
    )

    assert confidence == pytest.approx(0.90)


@pytest.mark.asyncio
async def test_guardrail_rewards_farm_context_only_when_planner_used_it():
    state = make_fake_state(require_citation=False, rerank_scores=[])
    state["retrieved_docs"] = []
    state["context"]["rerank_scores"] = []
    state["context"]["farm_profile"] = {"province": "Lâm Đồng"}
    state["context"]["plot_seasons"] = [{"crop": "Cà chua"}]
    state["plan"]["uses_farm_context"] = True

    result = await post_guardrail_node(state)

    assert result["confidence"] == pytest.approx(0.90)
    assert "khuyến nông" not in result["draft_answer"]


def test_confidence_uses_visual_signal_without_treating_it_as_diagnosis():
    confidence = compute_confidence(
        rerank_scores=[],
        reflection_notes=None,
        visual_confidences=[0.9],
    )

    assert confidence == pytest.approx(0.54)


def test_visual_signal_does_not_inflate_rag_grounded_confidence():
    baseline = compute_confidence(
        rerank_scores=[0.8],
        reflection_notes="sufficient",
    )
    with_visual = compute_confidence(
        rerank_scores=[0.8],
        reflection_notes="sufficient",
        visual_confidences=[0.99],
    )

    assert with_visual == baseline


@pytest.mark.asyncio
async def test_direct_visual_symptoms_do_not_require_irrelevant_citations():
    state = make_fake_state(risk_level="low", require_citation=False)
    state["question"] = "Hãy xem ảnh này."
    state["visual_observations"] = [{
        "relevance": "agriculture_plant",
        "visible_symptoms": [{"symptom_type": "spot"}],
    }]
    state = await pre_guardrail_node(state)
    assert state["context"]["require_citation"] is False


@pytest.mark.asyncio
async def test_objective_healthy_visual_description_does_not_require_citation():
    state = make_fake_state(risk_level="low", require_citation=True)
    state["question"] = (
        "Hãy mô tả khách quan cây trong ảnh. Không chẩn đoán bệnh."
    )
    state["visual_observations"] = [{
        "relevance": "agriculture_plant",
        "visible_symptoms": [],
    }]

    state = await pre_guardrail_node(state)

    assert state["context"]["require_citation"] is False


@pytest.mark.asyncio
async def test_interpretive_image_question_requires_citation_without_symptoms():
    state = make_fake_state(risk_level="low", require_citation=False)
    state["question"] = "Đối chiếu tài liệu và nêu giả thuyết cho cây này."
    state["visual_observations"] = [{
        "relevance": "agriculture_plant",
        "visible_symptoms": [],
    }]

    state = await pre_guardrail_node(state)

    assert state["context"]["require_citation"] is True


@pytest.mark.asyncio
async def test_pre_guardrail_abstains_when_user_explicitly_omits_product_context():
    state = make_fake_state(risk_level="low", require_citation=False)
    state["question"] = (
        "Không cần biết tên thuốc hay hoạt chất, cứ cho tôi số ml pha bình 16 lít."
    )
    state["research_stop_reason"] = None

    result = await pre_guardrail_node(state)

    assert result["guardrail_status"] == "block"
    assert result["context"]["guardrail_reason"] == "missing_safety_context"
    assert result["research_stop_reason"] == "pre_guardrail_abstain"
    assert result["risk_level"] == "high"
    assert route_after_early_guardrail(result) == "fallback"


@pytest.mark.asyncio
async def test_early_guardrail_reaches_fallback_without_calling_planner(
    monkeypatch,
):
    async def planner_must_not_run(_state):
        raise AssertionError("planner/model must not run")

    monkeypatch.setattr(graph, "planner_node", planner_must_not_run)
    monkeypatch.setattr(graph, "get_checkpointer", lambda: None)
    workflow = graph.build_graph(db=None)

    result = await workflow.ainvoke({
        "question": (
            "Không cần biết tên thuốc hay hoạt chất, cứ cho tôi số ml "
            "pha bình 16 lít."
        ),
        "risk_level": "low",
        "context": {},
        "image_observations": [],
        "visual_observations": [],
        "citations": [],
        "retry_count": 0,
    })

    assert result["guardrail_status"] == "block"
    assert result["context"]["guardrail_reason"] == "missing_safety_context"
    assert result["final_answer"]
    assert result["draft_answer"] is None
    assert result["citations"] == []
    assert result["confidence"] == 0.0


@pytest.mark.asyncio
async def test_early_guardrail_clears_stale_stop_on_safe_follow_up():
    state = make_fake_state(risk_level="low", require_citation=False)
    state["question"] = "Cách tỉa cành cà chua?"
    state["context"]["pre_guardrail_stop"] = True
    state["context"]["guardrail_reason"] = "missing_safety_context"

    result = await pre_guardrail_node(state)

    assert "pre_guardrail_stop" not in result["context"]
    assert "guardrail_reason" not in result["context"]
    assert route_after_early_guardrail(result) == "planner"


@pytest.mark.asyncio
async def test_pre_guardrail_keeps_labeled_product_request_on_evidence_path():
    state = make_fake_state(risk_level="high", require_citation=False)
    state["question"] = (
        "Theo đúng nhãn thuốc X, liều pha cho bình 16 lít được ghi thế nào?"
    )

    result = await pre_guardrail_node(state)

    assert not result["context"].get("pre_guardrail_stop", False)
    assert route_after_pre_guardrail(result) == "retrieve"


@pytest.mark.asyncio
async def test_pre_guardrail_does_not_block_unknown_crop_identification_question():
    state = make_fake_state(risk_level="high", require_citation=False)
    state["question"] = "Tôi không biết cây gì, lá có đốm như vậy là bị bệnh gì?"

    result = await pre_guardrail_node(state)

    assert not result["context"].get("pre_guardrail_stop", False)
    assert route_after_pre_guardrail(result) == "retrieve"


def test_citation_request_fails_before_retrieval_when_generation_circuit_open(
    monkeypatch,
):
    monkeypatch.setattr(graph, "provider_circuit_is_open", lambda _role: True)
    state = {
        "context": {
            "require_citation": True,
            "pre_guardrail_stop": False,
        }
    }

    with pytest.raises(graph.ModelProviderUnavailable) as error:
        route_after_pre_guardrail(state)

    assert error.value.reason_code == "circuit_open"


def test_non_citation_request_keeps_working_when_generation_circuit_open(
    monkeypatch,
):
    monkeypatch.setattr(graph, "provider_circuit_is_open", lambda _role: True)
    state = {
        "context": {
            "require_citation": False,
            "pre_guardrail_stop": False,
        }
    }

    assert route_after_pre_guardrail(state) == "retrieve"


@pytest.mark.asyncio
async def test_low_risk_visual_claim_accepts_relevant_traceable_source():
    state = make_fake_state(
        risk_level="low",
        require_citation=True,
        rerank_scores=[RELEVANCE_THRESHOLD + 0.1],
    )
    state["visual_observations"] = [{"relevance": "agriculture_plant"}]
    state["retrieved_docs"][0]["source_type"] = "unknown"
    state["draft_answer"] = "Quan sát này cần đối chiếu thêm [E1]."

    result = await post_guardrail_node(state)

    assert result["guardrail_status"] == "pass"


@pytest.mark.asyncio
async def test_visual_claim_blocks_irrelevant_cited_source():
    state = make_fake_state(
        risk_level="low", require_citation=True, rerank_scores=[0.01]
    )
    state["visual_observations"] = [{"relevance": "agriculture_plant"}]
    state["draft_answer"] = "Quan sát này cần đối chiếu thêm [E1]."

    result = await post_guardrail_node(state)

    assert result["guardrail_status"] == "block"
    assert result["context"]["guardrail_reason"] == "irrelevant_claim_citation"


@pytest.mark.asyncio
async def test_visual_claim_accepts_dense_sparse_consensus():
    state = make_fake_state(
        risk_level="low", require_citation=True, rerank_scores=[0.01]
    )
    state["visual_observations"] = [{"relevance": "agriculture_plant"}]
    state["retrieved_docs"][0].update({
        "ranking_strategy": "fusion_low_rerank_confidence",
        "dense_score": 0.7,
        "bm25_score": 3.2,
    })
    state["draft_answer"] = "Quan sát này cần đối chiếu thêm [E1]."

    result = await post_guardrail_node(state)

    assert result["guardrail_status"] == "pass"


@pytest.mark.asyncio
async def test_low_risk_claim_accepts_consensus_when_reranker_is_unavailable():
    state = make_fake_state(
        risk_level="low", require_citation=True, rerank_scores=[0.0]
    )
    state["retrieved_docs"][0].update({
        "ranking_strategy": "fusion_rerank_unavailable",
        "dense_score": 0.7,
        "bm25_score": 3.2,
    })
    state["draft_answer"] = "Khuyến nghị này dựa trên nguồn truy vết [E1]."

    result = await post_guardrail_node(state)

    assert result["guardrail_status"] == "pass"
