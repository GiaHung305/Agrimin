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
from app.services import semantic_cache
from app.services.semantic_cache import _context_key, is_realtime_sensitive_question
from app.workflow.nodes import planner, reflection


@pytest.fixture(autouse=True)
def reset_model_provider_circuit():
    model_gateway._reset_circuit_breakers()
    yield
    model_gateway._reset_circuit_breakers()


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


@pytest.mark.asyncio
async def test_cache_namespace_changes_with_corpus_version(monkeypatch):
    versions = iter(["4", "5"])

    async def get_version(key):
        assert key == semantic_cache.CORPUS_VERSION_KEY
        return next(versions)

    monkeypatch.setattr(semantic_cache.redis_client, "get", get_version)
    first = await semantic_cache._versioned_context_key("u1", None, None)
    second = await semantic_cache._versioned_context_key("u1", None, None)

    assert first.endswith(":corpus-4")
    assert second.endswith(":corpus-5")


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
async def test_planner_skips_retrieval_for_pure_natural_task_request(monkeypatch):
    async def decide(prompt):
        return planner.PlannerDecision(
            need_rag=True,
            need_weather=True,
            need_deep_research=True,
            risk_level="low",
            research_questions=["Có cần tưới cây không?"],
            action_intent="create_task",
        )

    monkeypatch.setattr(planner, "_call_gemini", decide)
    state = {
        "question": "Mai 6 giờ chiều báo mình tưới cà chua nhé",
        "context": {},
    }

    result = await planner.planner_node(state)

    assert result["plan"]["action_intent"] == "create_task"
    assert result["plan"]["need_rag"] is False
    assert result["plan"]["need_weather"] is False
    assert result["plan"]["need_deep_research"] is False
    assert result["research_questions"] == []


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
async def test_planner_does_not_promote_explicit_no_dosage_hypothesis_to_high(
    monkeypatch,
):
    async def decide(prompt):
        return planner.PlannerDecision(
            need_rag=True,
            need_weather=False,
            need_deep_research=False,
            risk_level="medium",
            research_questions=["Giả thuyết phù hợp với triệu chứng nhìn thấy"],
        )

    monkeypatch.setattr(planner, "_call_gemini", decide)
    state = {
        "question": (
            "Đối chiếu tài liệu và nêu giả thuyết; không đưa liều lượng xử lý."
        ),
        "context": {},
        "image_observations": [{}],
        "visual_observations": [{"relevance": "agriculture_plant"}],
    }

    result = await planner.planner_node(state)

    assert result["risk_level"] == "medium"


@pytest.mark.asyncio
async def test_planner_keeps_actual_treatment_request_high(monkeypatch):
    async def decide(prompt):
        return planner.PlannerDecision(
            need_rag=True,
            need_weather=False,
            need_deep_research=False,
            risk_level="medium",
        )

    monkeypatch.setattr(planner, "_call_gemini", decide)
    result = await planner.planner_node({
        "question": "Cây này bệnh gì và phun thuốc liều bao nhiêu ml?",
        "context": {},
    })

    assert result["risk_level"] == "high"


def test_conceptual_ipm_package_question_is_not_deterministically_high_risk():
    assert not planner._has_deterministic_high_risk_request(
        "IPM có phải một gói thuốc cố định không?"
    )


def test_conceptual_ipm_question_with_dosage_request_stays_high_risk():
    assert planner._has_deterministic_high_risk_request(
        "IPM có phải một gói thuốc cố định không? Nếu phun thì pha liều bao nhiêu ml?"
    )


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
async def test_reflection_skips_model_for_deterministic_action_reply(monkeypatch):
    async def fail_if_called(prompt):
        raise AssertionError("Action replies do not need model reflection")

    monkeypatch.setattr(reflection, "_call_gemini", fail_if_called)
    state = {
        "question": "Mai 6 giờ tối báo mình tưới cây nhé",
        "draft_answer": "Mình đã chuẩn bị lời nhắc.",
        "context": {"deterministic_action_response": True},
    }

    result = await reflection.reflection_node(state)

    assert result["reflection_notes"] == "sufficient"


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


@pytest.mark.asyncio
async def test_model_gateway_opens_role_circuit_after_consecutive_failures(
    monkeypatch,
):
    class QuotaModels:
        def __init__(self):
            self.calls = 0

        async def generate_content(self, **kwargs):
            self.calls += 1
            raise ClientError(
                429,
                {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED"}},
            )

    models = QuotaModels()
    fake_client = SimpleNamespace(aio=SimpleNamespace(models=models))
    monkeypatch.setattr(model_gateway, "client", fake_client)
    monkeypatch.setattr(
        model_gateway.settings, "model_circuit_failure_threshold", 2
    )
    monkeypatch.setattr(
        model_gateway.settings, "model_circuit_cooldown_seconds", 60.0
    )

    for _ in range(2):
        with pytest.raises(model_gateway.ModelProviderUnavailable):
            await model_gateway.generate_content(ModelRole.PLANNER, "prompt")

    with pytest.raises(
        model_gateway.ModelProviderUnavailable, match="circuit is temporarily open"
    ):
        await model_gateway.generate_content(ModelRole.PLANNER, "prompt")

    assert models.calls == 2


@pytest.mark.asyncio
async def test_model_gateway_success_resets_consecutive_failure_count(monkeypatch):
    class RecoveringModels:
        def __init__(self):
            self.calls = 0

        async def generate_content(self, **kwargs):
            self.calls += 1
            if self.calls in {1, 3}:
                raise ClientError(
                    429,
                    {
                        "error": {
                            "code": 429,
                            "status": "RESOURCE_EXHAUSTED",
                        }
                    },
                )
            return SimpleNamespace(text="ok")

    models = RecoveringModels()
    monkeypatch.setattr(
        model_gateway,
        "client",
        SimpleNamespace(aio=SimpleNamespace(models=models)),
    )
    monkeypatch.setattr(
        model_gateway.settings, "model_circuit_failure_threshold", 2
    )

    with pytest.raises(model_gateway.ModelProviderUnavailable):
        await model_gateway.generate_content(ModelRole.PLANNER, "prompt")
    response = await model_gateway.generate_content(ModelRole.PLANNER, "prompt")
    assert response.text == "ok"
    with pytest.raises(model_gateway.ModelProviderUnavailable):
        await model_gateway.generate_content(ModelRole.PLANNER, "prompt")

    assert models.calls == 3


def test_model_gateway_allows_one_half_open_probe_after_cooldown(monkeypatch):
    clock = iter([100.0, 101.0, 106.0, 107.0, 108.0])
    monkeypatch.setattr(model_gateway, "monotonic", lambda: next(clock))
    monkeypatch.setattr(
        model_gateway.settings, "model_circuit_failure_threshold", 1
    )
    monkeypatch.setattr(
        model_gateway.settings, "model_circuit_cooldown_seconds", 5.0
    )

    model_gateway._record_provider_failure(ModelRole.PLANNER)
    with pytest.raises(
        model_gateway.ModelProviderUnavailable, match="circuit is temporarily open"
    ):
        model_gateway._before_provider_call(ModelRole.PLANNER)

    model_gateway._before_provider_call(ModelRole.PLANNER)
    with pytest.raises(
        model_gateway.ModelProviderUnavailable, match="circuit is temporarily open"
    ):
        model_gateway._before_provider_call(ModelRole.PLANNER)

    model_gateway._record_provider_success(ModelRole.PLANNER)
    model_gateway._before_provider_call(ModelRole.PLANNER)
