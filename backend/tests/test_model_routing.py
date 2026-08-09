import os
import sys
import asyncio
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from google.genai.errors import ClientError
from pydantic import ValidationError

from app.core.model_registry import ModelRole, model_name, runtime_fingerprint
from app.services import model_gateway
from app.services.semantic_cache import _context_key, is_realtime_sensitive_question
from app.workflow.nodes import planner, reflection


def test_model_registry_resolves_roles_from_configuration(monkeypatch):
    monkeypatch.setattr(planner.settings, "model_planner", "planner-champion")
    monkeypatch.setattr(planner.settings, "model_generation", "generation-champion")
    assert model_name(ModelRole.PLANNER) == "planner-champion"
    assert model_name(ModelRole.GENERATION) == "generation-champion"


@pytest.mark.asyncio
async def test_planner_sends_json_schema_supported_by_gemini(monkeypatch):
    captured = {}

    async def fake_generate(role, contents, *, config):
        captured["config"] = config
        return SimpleNamespace(text='{"need_rag":true,"need_weather":false,"need_deep_research":false,"risk_level":"low","research_questions":[]}')

    monkeypatch.setattr(planner, "generate_content", fake_generate)
    await planner._call_gemini("question")
    assert captured["config"].response_json_schema is not None
    assert captured["config"].response_schema is None


def test_runtime_fingerprint_changes_with_policy(monkeypatch):
    before = runtime_fingerprint()
    monkeypatch.setattr(planner.settings, "ai_policy_version", "safety-v-next")
    assert runtime_fingerprint() != before


def test_cache_key_contains_runtime_and_time_versions():
    first = _context_key("u1", "Dak Lak", "coffee", time_window="2026080710")
    next_hour = _context_key("u1", "Dak Lak", "coffee", time_window="2026080711")
    assert first != next_hour
    assert runtime_fingerprint() in first


def test_realtime_questions_bypass_semantic_cache():
    assert is_realtime_sensitive_question("Thời tiết hôm nay có mưa không?")
    assert not is_realtime_sensitive_question("Cách tỉa cành cà chua")


def test_model_gateway_import_does_not_require_api_key(monkeypatch):
    monkeypatch.setattr(model_gateway, "client", None)
    monkeypatch.setattr(model_gateway.settings, "google_api_key", "")

    with pytest.raises(
        model_gateway.ModelProviderUnavailable,
        match="Google API key is not configured",
    ):
        model_gateway._get_client()


@pytest.mark.asyncio
async def test_planner_uses_typed_decision(monkeypatch):
    async def decide(prompt):
        return planner.PlannerDecision(
            need_rag=True,
            need_weather=True,
            need_deep_research=False,
            risk_level="medium",
        )

    monkeypatch.setattr(planner, "_call_gemini", decide)
    state = {"question": "Mưa có ảnh hưởng cây không?", "context": {}}
    result = await planner.planner_node(state)
    assert result["plan"]["need_weather"] is True
    assert result["risk_level"] == "medium"


@pytest.mark.asyncio
async def test_planner_invalid_output_falls_back_high_for_dosage(monkeypatch):
    async def invalid(prompt):
        try:
            planner.PlannerDecision.model_validate({"need_rag": "invalid"})
        except ValidationError as exc:
            raise exc

    monkeypatch.setattr(planner, "_call_gemini", invalid)
    state = {"question": "Pha thuốc bao nhiêu ml?", "context": {}}
    result = await planner.planner_node(state)
    assert result["risk_level"] == "high"
    assert result["plan"]["need_rag"] is True


@pytest.mark.asyncio
async def test_reflection_invalid_output_requests_more_evidence(monkeypatch):
    async def invalid(prompt):
        try:
            reflection.ReflectionDecision.model_validate({"status": "maybe"})
        except ValidationError as exc:
            raise exc

    monkeypatch.setattr(reflection, "_call_gemini", invalid)
    state = {
        "question": "Câu hỏi",
        "draft_answer": "Câu trả lời",
        "retrieved_docs": [],
        "retry_count": 0,
    }
    result = await reflection.reflection_node(state)
    assert result["reflection_notes"] == "need_more_search"
    assert result["retry_count"] == 0
    assert result["research_stop_reason"] == "answer_insufficient"


@pytest.mark.asyncio
async def test_model_gateway_translates_timeout_to_stable_error(monkeypatch):
    class SlowModels:
        async def generate_content(self, **kwargs):
            await asyncio.sleep(0.05)

    fake_client = SimpleNamespace(aio=SimpleNamespace(models=SlowModels()))
    monkeypatch.setattr(model_gateway, "client", fake_client)
    monkeypatch.setattr(model_gateway.settings, "model_request_timeout_seconds", 0.001)
    with pytest.raises(model_gateway.ModelProviderUnavailable):
        await model_gateway.generate_content(ModelRole.PLANNER, "prompt")


@pytest.mark.asyncio
async def test_model_gateway_translates_provider_quota_error(monkeypatch):
    class QuotaModels:
        async def generate_content(self, **kwargs):
            raise ClientError(
                429,
                {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED"}},
            )

    fake_client = SimpleNamespace(aio=SimpleNamespace(models=QuotaModels()))
    monkeypatch.setattr(model_gateway, "client", fake_client)

    with pytest.raises(model_gateway.ModelProviderUnavailable):
        await model_gateway.generate_content(ModelRole.PLANNER, "prompt")
