import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.workflow.nodes import generate, planner, post_guardrail, reflection


@pytest.mark.asyncio
async def test_casual_answer_flow_skips_models_and_uncertainty_warning(monkeypatch):
    async def fail_planner(*_args, **_kwargs):
        raise AssertionError("casual turn must not call planner model")

    async def fail_reflection(*_args, **_kwargs):
        raise AssertionError("casual turn must not call reflection model")

    async def fail_generation(*_args, **_kwargs):
        raise AssertionError("casual turn must not call generation model")
        yield

    monkeypatch.setattr(planner, "_call_gemini", fail_planner)
    monkeypatch.setattr(reflection, "_call_gemini", fail_reflection)
    monkeypatch.setattr(generate, "stream_content", fail_generation)

    state = {
        "question": "Cảm ơn bạn nhé!",
        "context": {},
        "tool_results": {},
        "retrieved_docs": [],
    }
    state = await planner.planner_node(state)
    state = await generate.generate_node(state)
    state = await reflection.reflection_node(state)
    state = await post_guardrail.post_guardrail_node(state)

    assert state["plan"]["need_rag"] is False
    assert state["plan"]["need_weather"] is False
    assert state["draft_answer"] == "Không có gì nhé."
    assert "khuyến nông" not in state["draft_answer"]
    assert state["reflection_notes"] == "sufficient"
    assert state["guardrail_status"] == "pass"
    assert state["confidence"] == 1.0
    assert state["context"]["deterministic_safe_response"] == "casual"
