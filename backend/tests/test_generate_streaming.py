import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.workflow.nodes import generate


async def fake_stream(*args, **kwargs):
    yield SimpleNamespace(text="Xin ")
    yield SimpleNamespace(text="chao")


async def cited_stream(*args, **kwargs):
    yield SimpleNamespace(text="Khuyen cao [E1]")


@pytest.mark.asyncio
async def test_generate_node_writes_tokens_for_low_risk_answer(monkeypatch):
    events = []
    monkeypatch.setattr(generate, "get_stream_writer", lambda: events.append)
    monkeypatch.setattr(generate, "stream_content", fake_stream)
    state = {
        "risk_level": "low",
        "retrieved_docs": [],
        "context": {},
        "tool_results": {},
        "question": "Xin chao",
    }

    result = await generate.generate_node(state)

    assert result["draft_answer"] == "Xin chao"
    assert events == [
        {"type": "token", "text": "Xin "},
        {"type": "token", "text": "chao"},
    ]


@pytest.mark.asyncio
async def test_generate_task_reply_is_friendly_truthful_and_skips_model(monkeypatch):
    events = []

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("Pure task requests must not call the answer model")
        yield

    monkeypatch.setattr(generate, "get_stream_writer", lambda: events.append)
    monkeypatch.setattr(generate, "stream_content", fail_if_called)
    state = {
        "risk_level": "low",
        "retrieved_docs": [],
        "context": {
            "action_request": {
                "intent": "create_task",
                "complete": True,
                "title": "Tưới cây",
                "due_at": "2026-08-21T18:00:00",
                "missing_fields": [],
                "pure_action": True,
            }
        },
        "tool_results": {},
        "question": "Mai 6 giờ tối báo mình tưới cây nhé",
    }

    result = await generate.generate_node(state)

    answer = result["draft_answer"]
    assert "Mình đã chuẩn bị lời nhắc" in answer
    assert "xác nhận" in answer.casefold()
    assert "đã tạo" not in answer.casefold()
    assert result["context"]["deterministic_action_response"] is True
    # Action replies are buffered until PendingAction persistence succeeds.
    assert events == []


@pytest.mark.asyncio
async def test_generate_prompt_prioritizes_current_farm_profile(monkeypatch):
    prompts = []

    async def capture_prompt(_role, contents, *args, **kwargs):
        prompts.append(contents)
        yield SimpleNamespace(text="Đã đọc hồ sơ.")

    monkeypatch.setattr(generate, "get_stream_writer", lambda: lambda event: None)
    monkeypatch.setattr(generate, "stream_content", capture_prompt)
    state = {
        "risk_level": "low",
        "retrieved_docs": [],
        "context": {
            "farm_profile": {
                "province": "Lâm Đồng",
                "area_ha": 1.0,
                "farming_style": "Normal",
            },
            "plot_seasons": [
                {
                    "plot_name": "Thửa A",
                    "crop": "Bắp Cải",
                    "growth_stage": "cây con",
                    "status": "active",
                }
            ],
            "known_facts": [],
        },
        "tool_results": {},
        "question": "Bạn có đọc được hồ sơ nông trại không?",
    }

    await generate.generate_node(state)

    assert '"province": "Lâm Đồng"' in prompts[0]
    assert '"crop": "Bắp Cải"' in prompts[0]
    assert "nguồn duy nhất" in prompts[0]


@pytest.mark.asyncio
async def test_generate_node_buffers_high_risk_answer(monkeypatch):
    events = []
    monkeypatch.setattr(generate, "get_stream_writer", lambda: events.append)
    monkeypatch.setattr(generate, "stream_content", fake_stream)
    state = {
        "risk_level": "high",
        "retrieved_docs": [],
        "context": {},
        "tool_results": {},
        "question": "Xin chao",
    }

    result = await generate.generate_node(state)

    assert result["draft_answer"] == "Xin chao"
    assert events == []


@pytest.mark.asyncio
async def test_generate_node_emits_traceable_citation_metadata(monkeypatch):
    monkeypatch.setattr(generate, "get_stream_writer", lambda: lambda event: None)
    monkeypatch.setattr(generate, "stream_content", cited_stream)
    state = {
        "risk_level": "low",
        "retrieved_docs": [{
            "document_id": "doc-1",
            "chunk_id": "chunk-2",
            "chunk_index": 2,
            "title": "Khuyến nông",
            "source": "https://example.test/doc",
            "version": "2026-08",
            "locator": "https://example.test/doc#page=3",
            "is_active": True,
            "content": "Nội dung",
            "fusion_score": 0.03,
            "rerank_score": 0.91,
        }],
        "context": {},
        "tool_results": {},
        "question": "Hỏi",
    }
    result = await generate.generate_node(state)
    citation = result["citations"][0]
    assert citation["document_id"] == "doc-1"
    assert citation["chunk_id"] == "chunk-2"
    assert citation["version"] == "2026-08"
    assert citation["rerank_score"] == 0.91
    assert citation["citation_id"] == "E1"


@pytest.mark.asyncio
async def test_generate_node_returns_only_claim_referenced_citations(monkeypatch):
    async def second_only(*args, **kwargs):
        yield SimpleNamespace(text="Quan sat duoc ho tro [E2] [E2]")

    monkeypatch.setattr(generate, "get_stream_writer", lambda: lambda event: None)
    monkeypatch.setattr(generate, "stream_content", second_only)
    state = {
        "risk_level": "low",
        "retrieved_docs": [
            {
                "document_id": f"doc-{index}",
                "chunk_id": f"chunk-{index}",
                "is_active": True,
                "content": "Noi dung",
                "rerank_score": 0.9,
            }
            for index in (1, 2)
        ],
        "context": {},
        "tool_results": {},
        "question": "Hoi",
    }

    result = await generate.generate_node(state)

    assert [item["citation_id"] for item in result["citations"]] == ["E2"]
    assert result["citations"][0]["document_id"] == "doc-2"


def test_visual_generation_excludes_evidence_that_failed_coverage():
    eligible = {
        "document_id": "doc-tomato",
        "chunk_id": "chunk-tomato",
        "is_active": True,
        "content": "Tài liệu cà chua",
        "source_type": "extension",
        "rerank_score": 0.2,
        "ranking_strategy": "rerank",
    }
    irrelevant = {
        "document_id": "doc-coffee",
        "chunk_id": "chunk-coffee",
        "is_active": True,
        "content": "Tài liệu cà phê",
        "source_type": "government",
        "rerank_score": 0.001,
        "ranking_strategy": "rerank",
    }
    state = {
        "risk_level": "medium",
        "visual_observations": [{"relevance": "agriculture_plant"}],
        "retrieved_docs": [irrelevant, eligible],
    }

    assert generate.answer_evidence_for_state(state) == [eligible]


def test_visual_generation_excludes_traceable_evidence_for_another_crop():
    lettuce = {
        "document_id": "doc-lettuce",
        "chunk_id": "chunk-lettuce",
        "title": "Xà lách - nhận biết độ thu hoạch",
        "is_active": True,
        "content": "Tài liệu xà lách",
        "source_type": "extension",
        "rerank_score": 0.9,
        "ranking_strategy": "rerank",
    }
    artichoke = {
        **lettuce,
        "document_id": "doc-artichoke",
        "chunk_id": "chunk-artichoke",
        "title": "Quy trình thu hoạch atisô",
        "content": "Tài liệu atisô",
    }
    state = {
        "risk_level": "medium",
        "visual_observations": [{"relevance": "agriculture_plant"}],
        "retrieved_docs": [artichoke, lettuce],
        "context": {
            "vision_retrieval_query": (
                "Sắp thu hoạch chưa? Quan sát thị giác: xà lách"
            )
        },
    }

    assert generate.answer_evidence_for_state(state) == [lettuce]


def test_high_risk_visual_generation_keeps_only_authoritative_high_relevance():
    authoritative = {
        "document_id": "doc-label",
        "chunk_id": "chunk-label",
        "is_active": True,
        "content": "Nhãn chính thức",
        "source_type": "government",
        "rerank_score": 0.8,
        "ranking_strategy": "rerank",
    }
    research = {
        **authoritative,
        "document_id": "doc-paper",
        "chunk_id": "chunk-paper",
        "source_type": "unknown",
    }
    state = {
        "risk_level": "high",
        "visual_observations": [{"relevance": "agriculture_plant"}],
        "retrieved_docs": [research, authoritative],
    }

    assert generate.answer_evidence_for_state(state) == [authoritative]


def test_high_risk_text_generation_keeps_only_authoritative_high_relevance():
    authoritative = {
        "document_id": "doc-government",
        "chunk_id": "chunk-government",
        "is_active": True,
        "content": "Quy trình chính thức",
        "source_type": "government",
        "rerank_score": 0.92,
        "ranking_strategy": "rerank",
    }
    unknown = {
        **authoritative,
        "document_id": "doc-unknown",
        "chunk_id": "chunk-unknown",
        "source_type": "unknown",
    }
    state = {
        "risk_level": "high",
        "visual_observations": [],
        "retrieved_docs": [unknown, authoritative],
    }

    assert generate.answer_evidence_for_state(state) == [authoritative]


def test_citation_required_text_generation_excludes_irrelevant_evidence():
    eligible = {
        "document_id": "doc-covered",
        "chunk_id": "chunk-covered",
        "is_active": True,
        "content": "Bằng chứng phù hợp",
        "source_type": "extension",
        "rerank_score": 0.75,
        "ranking_strategy": "rerank",
    }
    irrelevant = {
        **eligible,
        "document_id": "doc-irrelevant",
        "chunk_id": "chunk-irrelevant",
        "rerank_score": 0.001,
    }
    state = {
        "risk_level": "medium",
        "visual_observations": [],
        "context": {"require_citation": True},
        "retrieved_docs": [irrelevant, eligible],
    }

    assert generate.answer_evidence_for_state(state) == [eligible]


@pytest.mark.asyncio
async def test_citation_required_generation_repairs_marker_once_before_sse(
    monkeypatch,
):
    calls = 0
    events = []

    async def repair_stream(*args, **kwargs):
        nonlocal calls
        calls += 1
        text = "Giả thuyết ban đầu." if calls == 1 else "Giả thuyết [E1]."
        yield SimpleNamespace(text=text)

    monkeypatch.setattr(generate, "get_stream_writer", lambda: events.append)
    monkeypatch.setattr(generate, "stream_content", repair_stream)
    state = {
        "risk_level": "medium",
        "retrieved_docs": [{
            "document_id": "doc-1",
            "chunk_id": "chunk-1",
            "is_active": True,
            "content": "Bằng chứng",
            "source_type": "extension",
            "rerank_score": 0.8,
            "ranking_strategy": "rerank",
        }],
        "context": {"require_citation": True},
        "tool_results": {},
        "question": "Nêu giả thuyết có nguồn",
    }

    result = await generate.generate_node(state)

    assert calls == 2
    assert events == []
    assert result["draft_answer"] == "Giả thuyết [E1]."
    assert result["citations"][0]["citation_id"] == "E1"
    assert result["context"]["citation_repair_attempted"] is True


def test_research_coverage_detects_an_omitted_compound_branch():
    missing = generate.missing_research_question_coverage(
        "Cần kiểm tra vết xì mủ [E1].",
        [
            "Sầu riêng héo ngọn cần kiểm tra những gì",
            "Sầu riêng có biểu hiện xì mủ cần kiểm tra những gì",
        ],
    )

    assert missing == ["Sầu riêng héo ngọn cần kiểm tra những gì"]


def test_normalize_citation_markers_expands_combined_model_shorthand():
    assert generate.normalize_citation_markers(
        "Bón cân đối [E1, E5], quản lý nước [E3,  E4]."
    ) == "Bón cân đối [E1][E5], quản lý nước [E3][E4]."


@pytest.mark.asyncio
async def test_citation_required_generation_repairs_omitted_research_branch(
    monkeypatch,
):
    calls = 0

    async def repair_stream(*args, **kwargs):
        nonlocal calls
        calls += 1
        text = (
            "Kiểm tra xì mủ [E1]."
            if calls == 1
            else "Kiểm tra héo ngọn và xì mủ [E1]."
        )
        yield SimpleNamespace(text=text)

    monkeypatch.setattr(generate, "get_stream_writer", lambda: lambda event: None)
    monkeypatch.setattr(generate, "stream_content", repair_stream)
    state = {
        "risk_level": "medium",
        "retrieved_docs": [{
            "document_id": "doc-1",
            "chunk_id": "chunk-1",
            "is_active": True,
            "content": "Héo ngọn và xì mủ cần được kiểm tra.",
            "source_type": "government",
            "rerank_score": 0.9,
            "ranking_strategy": "rerank",
        }],
        "research_questions": [
            "Sầu riêng héo ngọn cần kiểm tra những gì",
            "Sầu riêng có biểu hiện xì mủ cần kiểm tra những gì",
        ],
        "context": {"require_citation": True},
        "tool_results": {},
        "question": "Sầu riêng héo ngọn hoặc xì mủ cần kiểm tra gì?",
    }

    result = await generate.generate_node(state)

    assert calls == 2
    assert result["draft_answer"] == "Kiểm tra héo ngọn và xì mủ [E1]."
    assert result["context"]["coverage_repair_attempted"] is True
    assert result["context"]["citation_repair_attempted"] is False
