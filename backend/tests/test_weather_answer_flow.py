import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.tools.weather_contract import local_weather_date
from app.workflow.nodes import generate, planner, retrieve


@pytest.mark.asyncio
async def test_weather_answer_flow_keeps_local_place_time_and_numbers(monkeypatch):
    requested_locations = []

    async def wrong_model_decision(_prompt):
        return planner.PlannerDecision(
            need_rag=True,
            need_weather=False,
            need_deep_research=True,
            risk_level="high",
            research_questions=["Không cần dùng"],
        )

    async def geocode(location):
        requested_locations.append(location)
        return 10.93, 108.10

    today = local_weather_date()

    async def weather(*_args):
        return {
            "forecast": [
                {
                    "date": today.isoformat(),
                    "temp_min": 25,
                    "temp_max": 32,
                    "rain_probability": 0.2,
                    "rain_mm": 0.5,
                },
                {
                    "date": (today + timedelta(days=1)).isoformat(),
                    "temp_min": 24.5,
                    "temp_max": 31.2,
                    "humidity_max": 88,
                    "description": "mưa rào",
                    "rain_probability": 0.73,
                    "rain_mm": 6.4,
                },
            ]
        }

    async def fail_if_answer_model_called(*_args, **_kwargs):
        raise AssertionError("pure weather answer must be deterministic")
        yield

    monkeypatch.setattr(planner, "_call_gemini", wrong_model_decision)
    monkeypatch.setattr(retrieve, "geocode_province_via_mcp", geocode)
    monkeypatch.setattr(retrieve, "get_weather_via_mcp", weather)
    monkeypatch.setattr(generate, "stream_content", fail_if_answer_model_called)

    state = {
        "question": "Bình Thuận ngày mai có mưa không?",
        "context": {},
        "tool_results": {},
    }
    state = await planner.planner_node(state)
    state = await retrieve.retrieve_node(state)
    state = await generate.generate_node(state)

    assert state["plan"]["need_weather"] is True
    assert state["plan"]["need_rag"] is False
    assert requested_locations == ["Phan Thiet"]
    assert state["context"]["weather_location_used"] == "Phan Thiet"
    assert "Ngày mai" in state["draft_answer"]
    assert "24,5–31,2°C" in state["draft_answer"]
    assert "khả năng mưa cao nhất 73%" in state["draft_answer"]
    assert "lượng mưa dự báo 6,4 mm" in state["draft_answer"]
    assert "Hôm nay" not in state["draft_answer"]
    assert state["context"]["deterministic_safe_response"] == "weather_forecast"
