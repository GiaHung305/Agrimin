import os
import sys
from datetime import timedelta
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.workflow.nodes import generate
from app.tools.weather_contract import local_weather_date


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
        "question": "Bạn là ai?",
    }

    result = await generate.generate_node(state)

    assert result["draft_answer"] == "Xin chao"
    assert events == [
        {"type": "token", "text": "Xin "},
        {"type": "token", "text": "chao"},
    ]


@pytest.mark.asyncio
async def test_generate_casual_reply_is_friendly_and_skips_model(monkeypatch):
    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("casual reply must not call the answer model")
        yield

    monkeypatch.setattr(generate, "stream_content", fail_if_called)
    state = {
        "risk_level": "low",
        "retrieved_docs": [],
        "context": {"casual_response_kind": "greeting"},
        "tool_results": {},
        "question": "Xin chào!",
    }

    result = await generate.generate_node(state)

    assert result["draft_answer"].startswith("Chào bạn!")
    assert "khuyến nông" not in result["draft_answer"]
    assert result["context"]["deterministic_safe_response"] == "casual"
    assert result["citations"] == []


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
@pytest.mark.parametrize(
    "context,expected_text",
    [
        ({}, "tỉnh hoặc thành phố nào"),
        (
            {"weather_location_candidates": ["Hanoi", "Da Nang"]},
            "nhiều địa điểm",
        ),
    ],
)
async def test_generate_weather_clarification_is_deterministic_and_friendly(
    monkeypatch, context, expected_text
):
    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("weather clarification must not call the model")
        yield

    monkeypatch.setattr(generate, "stream_content", fail_if_called)
    state = {
        "risk_level": "low",
        "retrieved_docs": [],
        "context": context,
        "plan": {"need_rag": False, "need_weather": True},
        "tool_results": {},
        "question": "Thời tiết hôm nay thế nào?",
    }

    result = await generate.generate_node(state)

    assert expected_text in result["draft_answer"]
    assert (
        result["context"]["deterministic_safe_response"]
        == "weather_clarification"
    )
    assert result["citations"] == []


@pytest.mark.asyncio
async def test_generate_weather_only_failure_does_not_invent_forecast(monkeypatch):
    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("failed weather-only request must not call the model")
        yield

    monkeypatch.setattr(generate, "stream_content", fail_if_called)
    state = {
        "risk_level": "low",
        "retrieved_docs": [],
        "context": {"weather_location": "Da Lat"},
        "plan": {"need_rag": False, "need_weather": True},
        "tool_results": {},
        "question": "Thời tiết ở Đà Lạt hôm nay thế nào?",
    }

    result = await generate.generate_node(state)

    assert "chưa lấy được dự báo" in result["draft_answer"]
    assert "thử lại sau ít phút" in result["draft_answer"]
    assert result["context"]["deterministic_safe_response"] == (
        "weather_unavailable"
    )


@pytest.mark.asyncio
async def test_generate_pure_weather_answer_preserves_validated_numbers_without_model(
    monkeypatch,
):
    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("pure weather must not be restated by a model")
        yield

    monkeypatch.setattr(generate, "stream_content", fail_if_called)
    today = local_weather_date()
    state = {
        "risk_level": "low",
        "retrieved_docs": [],
        "context": {"weather_location_used": "Da Lat"},
        "plan": {"need_rag": False, "need_weather": True},
        "tool_results": {
            "weather": {
                "forecast": [
                    {
                        "date": today.isoformat(),
                        "temp": 27.2,
                        "temp_min": 21.5,
                        "temp_max": 30.4,
                        "humidity": 76,
                        "humidity_max": 91,
                        "description": "mưa nhẹ",
                        "rain_probability": 0.67,
                        "rain_mm": 4.8,
                    },
                    {
                        "date": (today + timedelta(days=1)).isoformat(),
                        "temp": 28,
                        "temp_min": 22,
                        "temp_max": 31,
                        "humidity": 70,
                        "humidity_max": 85,
                        "description": "ít mây",
                        "rain_probability": 0.2,
                        "rain_mm": 0,
                    },
                ]
            }
        },
        "question": "Thời tiết Đà Lạt hôm nay thế nào?",
    }

    result = await generate.generate_node(state)

    answer = result["draft_answer"]
    assert "Dự báo cho Da Lat" in answer
    assert "21,5–30,4°C" in answer
    assert "khả năng mưa cao nhất 67%" in answer
    assert "lượng mưa dự báo 4,8 mm" in answer
    assert "độ ẩm cao nhất 91%" in answer
    assert "Ngày mai" not in answer
    assert result["context"]["deterministic_safe_response"] == "weather_forecast"
    assert result["citations"] == []


@pytest.mark.asyncio
async def test_generate_location_follow_up_keeps_original_weather_time_scope(
    monkeypatch,
):
    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("pure weather must not call the model")
        yield

    monkeypatch.setattr(generate, "stream_content", fail_if_called)
    today = local_weather_date()
    forecast = []
    for offset in range(2):
        forecast.append({
            "date": (today + timedelta(days=offset)).isoformat(),
            "temp_min": 20 + offset,
            "temp_max": 29 + offset,
            "rain_probability": 0.1 * offset,
            "rain_mm": 0,
        })
    state = {
        "risk_level": "low",
        "retrieved_docs": [],
        "context": {
            "weather_location_used": "Da Lat",
            "weather_location_follow_up": True,
            "conversation_history": [
                {"role": "user", "content": "Ngày mai có mưa không?"},
                {
                    "role": "assistant",
                    "content": "Bạn muốn xem thời tiết ở tỉnh hoặc thành phố nào?",
                },
            ],
        },
        "plan": {"need_rag": False, "need_weather": True},
        "tool_results": {"weather": {"forecast": forecast}},
        "question": "Đà Lạt",
    }

    result = await generate.generate_node(state)

    assert "Ngày mai" in result["draft_answer"]
    assert "Hôm nay" not in result["draft_answer"]
    assert "21–30°C" in result["draft_answer"]


@pytest.mark.asyncio
async def test_generate_location_follow_up_uses_new_time_scope_over_history(
    monkeypatch,
):
    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("pure weather must not call the model")
        yield

    monkeypatch.setattr(generate, "stream_content", fail_if_called)
    today = local_weather_date()
    forecast = [
        {
            "date": (today + timedelta(days=offset)).isoformat(),
            "temp_min": 20 + offset,
            "temp_max": 29 + offset,
            "rain_probability": 0.1 * offset,
            "rain_mm": 0,
        }
        for offset in range(2)
    ]
    state = {
        "risk_level": "low",
        "retrieved_docs": [],
        "context": {
            "weather_location_used": "Da Lat",
            "weather_location_follow_up": True,
            "conversation_history": [
                {"role": "user", "content": "Hôm nay có mưa không?"},
                {
                    "role": "assistant",
                    "content": "Bạn muốn xem thời tiết ở tỉnh hoặc thành phố nào?",
                },
            ],
        },
        "plan": {"need_rag": False, "need_weather": True},
        "tool_results": {"weather": {"forecast": forecast}},
        "question": "Đà Lạt ngày mai",
    }

    result = await generate.generate_node(state)

    assert "Ngày mai" in result["draft_answer"]
    assert "Hôm nay" not in result["draft_answer"]
    assert "21–30°C" in result["draft_answer"]


@pytest.mark.asyncio
async def test_generate_invalid_weather_payload_fails_closed_without_model(
    monkeypatch,
):
    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("invalid weather must not enter the answer model")
        yield

    monkeypatch.setattr(generate, "stream_content", fail_if_called)
    state = {
        "risk_level": "low",
        "retrieved_docs": [],
        "context": {"weather_location": "Da Lat"},
        "plan": {"need_rag": False, "need_weather": True},
        "tool_results": {
            "weather": {
                "forecast": [{
                    "date": local_weather_date().isoformat(),
                    "temp_min": 40,
                    "temp_max": 20,
                    "rain_probability": 0.2,
                    "rain_mm": 0,
                }]
            }
        },
        "question": "Thời tiết Đà Lạt hôm nay thế nào?",
    }

    result = await generate.generate_node(state)

    assert "chưa lấy được dự báo" in result["draft_answer"]
    assert "weather" not in result["tool_results"]
    assert result["context"]["weather_validation_error"] == "invalid_data"


@pytest.mark.asyncio
async def test_generate_prompt_names_the_weather_location_used(monkeypatch):
    prompts = []

    async def capture_prompt(_role, contents, *args, **kwargs):
        prompts.append(contents)
        yield SimpleNamespace(text="Dự báo đã được tạo.")

    monkeypatch.setattr(generate, "get_stream_writer", lambda: lambda _event: None)
    monkeypatch.setattr(generate, "stream_content", capture_prompt)
    today = local_weather_date()
    state = {
        "risk_level": "low",
        "retrieved_docs": [],
        "context": {"weather_location_used": "Da Lat"},
        "plan": {"need_rag": True, "need_weather": True},
        "tool_results": {
            "weather": {
                "forecast": [{
                    "date": today.isoformat(),
                    "temp_min": 21,
                    "temp_max": 30,
                    "description": "nắng nhẹ",
                    "rain_probability": 0.1,
                    "rain_mm": 0,
                }]
            }
        },
        "question": "Thời tiết ảnh hưởng tưới cà phê thế nào?",
    }

    await generate.generate_node(state)

    assert "Địa điểm dùng cho dự báo thời tiết: Da Lat" in prompts[0]
    assert "'description': 'nắng nhẹ'" in prompts[0]


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
                "name": "Tên nông trại riêng tư",
                "province": "Lâm Đồng",
                "area_ha": 1.0,
                "farming_style": "Normal",
            },
            "plot_seasons": [
                {
                    "plot_id": "private-plot-id",
                    "season_id": "private-season-id",
                    "plot_name": "Thửa A",
                    "crop": "Bắp Cải",
                    "growth_stage": "cây con",
                    "location_note": "tọa độ riêng tư",
                    "status": "active",
                }
            ],
            "known_facts": [],
        },
        "plan": {"uses_farm_context": True},
        "tool_results": {},
        "question": "Bạn có đọc được hồ sơ nông trại không?",
    }

    await generate.generate_node(state)

    normalized_prompt = " ".join(prompts[0].split())
    assert '"province": "Lâm Đồng"' in prompts[0]
    assert '"crop": "Bắp Cải"' in prompts[0]
    assert "Tên nông trại riêng tư" not in prompts[0]
    assert "private-plot-id" not in prompts[0]
    assert "private-season-id" not in prompts[0]
    assert "tọa độ riêng tư" not in prompts[0]
    assert "nguồn duy nhất" in prompts[0]
    assert "chỉ trả lời các bước kiểm tra" in prompts[0]
    assert "bón cân đối dựa trên phân tích đất và nhu cầu cây" in normalized_prompt


@pytest.mark.asyncio
async def test_generate_prompt_omits_irrelevant_saved_farm_context(monkeypatch):
    prompts = []

    async def capture_prompt(_role, contents, *args, **kwargs):
        prompts.append(contents)
        yield SimpleNamespace(text="Câu trả lời ngắn [E1].")

    monkeypatch.setattr(generate, "get_stream_writer", lambda: lambda event: None)
    monkeypatch.setattr(generate, "stream_content", capture_prompt)
    state = {
        "risk_level": "high",
        "retrieved_docs": [{
            "document_id": "doc-1",
            "chunk_id": "chunk-1",
            "is_active": True,
            "source_type": "government",
            "content": "Bằng chứng phù hợp.",
            "rerank_score": 0.95,
            "ranking_strategy": "rerank",
        }],
        "context": {
            "farm_profile": {"province": "Lâm Đồng"},
            "plot_seasons": [{"crop": "Cà chua", "status": "active"}],
            "known_facts": [],
            "require_citation": True,
        },
        "plan": {"uses_farm_context": False},
        "research_questions": ["Dứa bị thối nõn có dấu hiệu gì?"],
        "tool_results": {},
        "question": "Dứa bị thối nõn có dấu hiệu gì?",
    }

    await generate.generate_node(state)

    assert '"province": "Lâm Đồng"' not in prompts[0]
    assert '"crop": "Cà chua"' not in prompts[0]
    assert "không dùng hồ sơ hoặc mùa vụ đã lưu" in prompts[0]
    assert "180-300 từ" in prompts[0]
    assert "Không mở đầu bằng lời chào xã giao" in prompts[0]


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


@pytest.mark.asyncio
async def test_citation_required_generation_repairs_uncited_technical_claim(
    monkeypatch,
):
    calls = 0

    async def repair_stream(*args, **kwargs):
        nonlocal calls
        calls += 1
        text = (
            "Thoát nước để hạn chế úng [E1]. Bón thêm đạm."
            if calls == 1
            else "Thoát nước để hạn chế úng [E1]. Bón cân đối [E1]."
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
            "content": "Thoát nước và bón cân đối theo phân tích đất.",
            "source_type": "government",
            "rerank_score": 0.9,
            "ranking_strategy": "rerank",
        }],
        "context": {"require_citation": True},
        "tool_results": {},
        "question": "Cần làm gì?",
    }

    result = await generate.generate_node(state)

    assert calls == 2
    assert result["draft_answer"] == (
        "Thoát nước để hạn chế úng [E1]. Bón cân đối [E1]."
    )
    assert result["context"]["claim_citation_repair_attempted"] is True


@pytest.mark.asyncio
async def test_generation_prunes_residual_uncited_claim_after_one_repair(
    monkeypatch,
):
    calls = 0

    async def stubborn_stream(*args, **kwargs):
        nonlocal calls
        calls += 1
        yield SimpleNamespace(
            text=(
                "Thoát nước để hạn chế úng [E1]. "
                "Nên phun thuốc ngay khi thấy lá vàng."
            )
        )

    monkeypatch.setattr(generate, "get_stream_writer", lambda: lambda event: None)
    monkeypatch.setattr(generate, "stream_content", stubborn_stream)
    state = {
        "risk_level": "medium",
        "retrieved_docs": [{
            "document_id": "doc-1",
            "chunk_id": "chunk-1",
            "is_active": True,
            "content": "Thoát nước để hạn chế úng.",
            "source_type": "government",
            "rerank_score": 0.9,
            "ranking_strategy": "rerank",
        }],
        "context": {"require_citation": True},
        "tool_results": {},
        "question": "Cần làm gì?",
    }

    result = await generate.generate_node(state)

    assert calls == 2
    assert result["draft_answer"] == "Thoát nước để hạn chế úng [E1]."
    assert result["context"]["uncited_claim_prune_count"] == 1
    assert result["citations"][0]["citation_id"] == "E1"


@pytest.mark.asyncio
async def test_buffered_entailment_repair_removes_the_rejected_claim_once(
    monkeypatch,
):
    prompts = []

    async def repair_stream(role, contents, **kwargs):
        prompts.append(contents)
        yield SimpleNamespace(text="Thoát nước để hạn chế úng [E1].")

    monkeypatch.setattr(generate, "get_stream_writer", lambda: lambda event: None)
    monkeypatch.setattr(generate, "stream_content", repair_stream)
    state = {
        "risk_level": "medium",
        "retrieved_docs": [{
            "document_id": "doc-1",
            "chunk_id": "chunk-1",
            "is_active": True,
            "content": "Cần thoát nước tốt để hạn chế úng.",
            "source_type": "government",
            "rerank_score": 0.9,
            "ranking_strategy": "rerank",
        }],
        "context": {
            "require_citation": True,
            "claim_entailment_failed": True,
            "unsupported_claims": ["Bón thêm đạm để cây hồi phục."],
        },
        "tool_results": {},
        "question": "Cần làm gì?",
    }

    result = await generate.generate_node(state)

    assert len(prompts) == 1
    assert "Bón thêm đạm để cây hồi phục." in prompts[0]
    assert result["draft_answer"] == "Thoát nước để hạn chế úng [E1]."
    assert result["context"]["entailment_repair_attempted"] is True


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
