import json
import os
import sys
from contextlib import contextmanager
from unittest.mock import AsyncMock

import pytest
from google.genai.errors import ServerError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.api import chat
from app.api.chat import _provider_unavailable_response


def test_provider_unavailable_response_is_stable_and_safe():
    response = _provider_unavailable_response("conversation-1")
    assert response["guardrail_status"] == "block"
    assert response["confidence"] == 0.0
    assert response["citations"] == []
    assert response["conversation_id"] == "conversation-1"


@pytest.mark.asyncio
async def test_provider_503_becomes_safe_sse_instead_of_http_500(monkeypatch):
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
            raise ServerError(503, {"error": {"message": "overloaded"}})

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

    assert events[0]["type"] == "chunk"
    assert "tạm thời quá tải" in events[0]["payload"]
    metadata = next(event["payload"] for event in events if event["type"] == "meta")
    assert metadata["guardrail_status"] == "block"
    assert metadata["confidence"] == 0.0
    assert events[-1]["type"] == "done"
