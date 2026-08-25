import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.workflow.confidence import compute_confidence
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
