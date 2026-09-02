import json
import os
import sys
from contextlib import contextmanager
from unittest.mock import AsyncMock

import pytest
from google.genai.errors import ServerError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.api.routes import chat
from app.api.routes.chat import _provider_unavailable_response
from app.services.model_gateway import ModelProviderUnavailable


def test_provider_unavailable_response_is_stable_and_safe():
    response = _provider_unavailable_response("conversation-1")
    assert response["guardrail_status"] == "block"
    assert response["confidence"] == 0.0
    assert response["citations"] == []
    assert response["conversation_id"] == "conversation-1"
    assert response["trace"]["guardrail"]["response_kind"] == "service_status"


@pytest.mark.parametrize(
    ("node", "message"),
    [
        ("planner", "Đang tìm thông tin phù hợp…"),
        ("retrieve", "Đang đối chiếu nguồn đáng tin cậy…"),
        ("research_analysis", "Đang soạn câu trả lời…"),
        ("reflection", "Đang kiểm tra câu trả lời…"),
        ("post_guardrail", "Đang hoàn tất câu trả lời…"),
    ],
)
def test_graph_nodes_map_to_non_technical_progress(node, message):
    assert chat._progress_after_nodes({node: {}}) == message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        ServerError(503, {"error": {"message": "overloaded"}}),
        ModelProviderUnavailable(
            "generation circuit open", reason_code="circuit_open"
        ),
    ],
    ids=["provider-503", "generation-circuit-open"],
)
async def test_provider_failure_becomes_safe_sse_instead_of_http_500(
    monkeypatch,
    failure,
):
    prepared = chat.PreparedChat(
        user_id="00000000-0000-0000-0000-000000000001",
        conversation_id="conversation-1",
        known_facts=[],
        known_province=None,
        known_crop=None,
        conversation_history=[],
        initial_state=chat._new_agent_state(
            "00000000-0000-0000-0000-000000000001",
            "conversation-1",
            "Cách tưới cà chua?",
            [],
            None,
            [],
            False,
        ),
        cached_response=None,
    )

    class BrokenGraph:
        async def astream(self, *_args, **_kwargs):
            if False:
                yield None
            raise failure

    @contextmanager
    def trace_context(**_kwargs):
        yield

    monkeypatch.setattr(
        chat,
        "_prepare_visual_input",
        AsyncMock(return_value=chat.PreparedVisualInput([], [], None)),
    )
    monkeypatch.setattr(chat, "_prepare_chat", AsyncMock(return_value=prepared))
    monkeypatch.setattr(chat, "build_graph", lambda _db: BrokenGraph())
    monkeypatch.setattr(chat, "get_langfuse_handler", lambda: None)
    monkeypatch.setattr(chat, "propagate_attributes", trace_context)

    response = await chat.chat_stream.__wrapped__(
        request=None,
        req=chat.ChatRequest(question="Cách tưới cà chua?"),
        db=object(),
        current_user={
            "id": "00000000-0000-0000-0000-000000000001",
            "email": "user@example.com",
        },
    )
    events = [
        json.loads(item.strip().removeprefix("data: "))
        async for item in response.body_iterator
        if item.strip().startswith("data: ")
    ]

    assert events[0] == {
        "type": "progress",
        "payload": "Đang hiểu câu hỏi…",
    }
    answer_event = next(event for event in events if event["type"] == "chunk")
    assert "tạm thời quá tải" in answer_event["payload"]
    metadata = next(event["payload"] for event in events if event["type"] == "meta")
    assert metadata["guardrail_status"] == "block"
    assert metadata["confidence"] == 0.0
    assert events[-1]["type"] == "done"
