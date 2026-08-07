import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.api import chat


def test_only_stream_chat_route_is_exposed():
    paths = {route.path for route in chat.router.routes}
    assert "/chat/stream" in paths
    assert "/chat" not in paths


def test_stream_request_supports_opt_in_deep_research():
    request = chat.ChatRequest(question="Nghiên cứu sâu về bệnh cây", deep_research=True)
    assert request.deep_research is True


def test_new_agent_state_contains_internal_research_contract():
    state = chat._new_agent_state(
        "user-1",
        "conversation-1",
        "Cách trồng cà chua?",
        [],
        None,
        [],
        False,
    )

    assert state["research_questions"] == []
    assert state["research_coverage"] == []
    assert state["missing_evidence"] == []
    assert state["evidence_conflicts"] == []
    assert state["research_stop_reason"] is None
    assert state["image_observations"] == []
    assert state["visual_observations"] == []
    assert state["context"]["vision_error"] is None
