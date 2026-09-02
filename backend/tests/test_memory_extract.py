import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from pydantic import ValidationError

from app.services.model_gateway import ModelProviderUnavailable
from app.workflow.nodes import memory_extract


class FakeSession:
    def __init__(self):
        self.added = []
        self.committed = False

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.committed = True


def test_memory_extraction_requires_flag_to_match_extracted_fields():
    with pytest.raises(ValidationError):
        memory_extract.MemoryExtraction(has_personal_info=True)

    with pytest.raises(ValidationError):
        memory_extract.MemoryExtraction(
            has_personal_info=False,
            province="Lâm Đồng",
        )

    assert memory_extract.MemoryExtraction(
        has_personal_info=False
    ).province is None


def test_memory_extraction_accepts_typed_retraction_and_rejects_conflicts():
    retraction = memory_extract.MemoryExtraction(
        has_personal_info=True,
        clear_fields=["crop"],
    )
    assert retraction.clear_fields == ["crop"]

    with pytest.raises(ValidationError):
        memory_extract.MemoryExtraction(
            has_personal_info=True,
            crop="Cà chua",
            clear_fields=["crop"],
        )

    with pytest.raises(ValidationError):
        memory_extract.MemoryExtraction(
            has_personal_info=True,
            clear_fields=["province", "province"],
        )


@pytest.mark.parametrize("area_ha", [0, -1, float("nan"), float("inf")])
def test_memory_extraction_rejects_invalid_area(area_ha):
    with pytest.raises(ValidationError):
        memory_extract.MemoryExtraction(
            has_personal_info=True,
            area_ha=area_ha,
        )


def test_memory_extraction_rejects_blank_or_oversized_text():
    with pytest.raises(ValidationError):
        memory_extract.MemoryExtraction(
            has_personal_info=True,
            crop="   ",
        )

    with pytest.raises(ValidationError):
        memory_extract.MemoryExtraction(
            has_personal_info=True,
            province="x" * 121,
        )


@pytest.mark.asyncio
async def test_memory_fact_uses_graph_confidence(monkeypatch):
    async def extract(prompt):
        return memory_extract.MemoryExtraction(
            has_personal_info=True, province="Dak Lak", crop="ca phe"
        )

    monkeypatch.setattr(memory_extract, "_call_gemini", extract)
    db = FakeSession()
    state = {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "question": "Toi trong ca phe o Dak Lak",
        "confidence": 0.63,
        "guardrail_status": "pass",
    }

    await memory_extract.memory_extract_node(state, db)

    assert db.committed
    assert len(db.added) == 1
    assert db.added[0].confidence == 0.63


@pytest.mark.asyncio
async def test_memory_extraction_skips_blocked_answer(monkeypatch):
    async def should_not_run(prompt):
        raise AssertionError("extractor must not run for blocked answers")

    monkeypatch.setattr(memory_extract, "_call_gemini", should_not_run)
    db = FakeSession()
    state = {"guardrail_status": "block", "question": "unsafe"}
    await memory_extract.memory_extract_node(state, db)
    assert not db.added
    assert not db.committed


@pytest.mark.asyncio
async def test_memory_extraction_skips_question_without_user_owned_fact(monkeypatch):
    async def should_not_run(prompt):
        raise AssertionError("extractor must not run without first-person context")

    monkeypatch.setattr(memory_extract, "_call_gemini", should_not_run)
    db = FakeSession()
    state = {
        "guardrail_status": "pass",
        "question": "Cách tưới cà chua trong chậu?",
    }

    await memory_extract.memory_extract_node(state, db)

    assert not db.added
    assert not db.committed


@pytest.mark.asyncio
async def test_memory_extraction_skips_deterministic_weather_status(monkeypatch):
    async def should_not_run(_prompt):
        raise AssertionError("weather clarification must not write memory")

    monkeypatch.setattr(memory_extract, "_call_gemini", should_not_run)
    db = FakeSession()
    state = {
        "guardrail_status": "pass",
        "question": "Thời tiết chỗ tôi hôm nay thế nào?",
        "context": {"deterministic_safe_response": "weather_status"},
    }

    await memory_extract.memory_extract_node(state, db)

    assert not db.added
    assert not db.committed


@pytest.mark.asyncio
async def test_memory_extraction_provider_failure_does_not_break_approved_answer(
    monkeypatch,
):
    async def unavailable(_prompt):
        raise ModelProviderUnavailable("provider unavailable")

    monkeypatch.setattr(memory_extract, "_call_gemini", unavailable)
    db = FakeSession()
    state = {
        "guardrail_status": "pass",
        "question": "Tôi trồng cà phê ở Đắk Lắk.",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "confidence": 0.8,
    }

    result = await memory_extract.memory_extract_node(state, db)

    assert result is state
    assert not db.added
    assert not db.committed


@pytest.mark.asyncio
async def test_memory_extractor_prompt_forbids_negated_or_inferred_facts(
    monkeypatch,
):
    captured = []

    async def extract(prompt):
        captured.append(prompt)
        return memory_extract.MemoryExtraction(has_personal_info=False)

    monkeypatch.setattr(memory_extract, "_call_gemini", extract)
    db = FakeSession()
    state = {
        "guardrail_status": "pass",
        "question": "Tôi không trồng cà phê ở Đắk Lắk.",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "confidence": 0.8,
    }

    await memory_extract.memory_extract_node(state, db)

    assert "không chép giá trị bị phủ định" in captured[0]
    assert "clear_fields" in captured[0]
    assert not db.added
    assert not db.committed
