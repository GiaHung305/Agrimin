import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.services import semantic_cache


def test_question_signature_distinguishes_requested_task():
    cause = semantic_cache.question_signature(
        "Dứa bị thối nõn do đâu?"
    )
    treatment = semantic_cache.question_signature(
        "Dứa bị thối nõn xử lý thế nào?"
    )

    assert cause != treatment
    assert "cause" in cause
    assert "treatment" in treatment


def test_question_signature_normalizes_vietnamese_case_and_accents():
    assert semantic_cache.question_signature(
        "VÌ SAO CÂY BỊ HÉO?"
    ) == semantic_cache.question_signature(
        "vi sao cay bi heo?"
    )


def test_question_signature_distinguishes_explicit_safety_exclusion():
    without_chemicals = semantic_cache.question_signature(
        "Cách xử lý bệnh, không nêu thuốc hoặc hóa chất."
    )
    with_chemicals = semantic_cache.question_signature(
        "Cách xử lý bệnh và nêu thuốc phù hợp."
    )

    assert without_chemicals != with_chemicals
    assert json.loads(without_chemicals)["safety_exclusion"] is True
    assert json.loads(with_chemicals)["safety_exclusion"] is False


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("Làm sao cứu cây đang héo?", "treatment"),
        ("Cách phòng bệnh thối nõn?", "prevention"),
        ("Khi nào nên thu hoạch?", "timing"),
    ],
)
def test_question_signature_covers_common_vietnamese_intents(question, intent):
    assert intent in json.loads(
        semantic_cache.question_signature(question)
    )["intents"]


def test_question_signature_marks_common_negative_and_yes_no_forms():
    negative = json.loads(
        semantic_cache.question_signature("Không sử dụng thuốc, xử lý cách khác.")
    )
    yes_no = json.loads(
        semantic_cache.question_signature("Có nên tưới thêm nước không?")
    )

    assert negative["negative_constraint"] is True
    assert negative["safety_exclusion"] is True
    assert yes_no["yes_no"] is True


def test_question_signature_contains_only_fixed_privacy_safe_labels():
    signature = semantic_cache.question_signature(
        "Vườn dứa riêng của anh Minh ở thửa Bí Mật bị thối nõn do đâu?"
    )
    decoded = json.loads(signature)

    assert decoded == {
        "intents": ["cause"],
        "negative_constraint": False,
        "safety_exclusion": False,
        "yes_no": False,
    }
    assert "minh" not in signature
    assert "bi mat" not in signature
    assert "dua" not in signature


@pytest.mark.asyncio
async def test_cache_rejects_same_vector_when_question_signature_differs(
    monkeypatch,
):
    async def fixed_context_key(*_args, **_kwargs):
        return "ctx"

    requested_keys = []
    cached_index = [{
        "answer_key": "answer:cause",
        "vector": [1.0, 0.0],
        "question_signature": semantic_cache.question_signature(
            "Dứa bị thối nõn do đâu?"
        ),
    }]

    async def fake_get(key):
        requested_keys.append(key)
        if key == "semcache_index:ctx":
            return json.dumps(cached_index)
        if key == "answer:cause":
            return json.dumps({"answer": "Nguyên nhân đã lưu"})
        return None

    async def fixed_embedding(_question):
        return [1.0, 0.0]

    monkeypatch.setattr(semantic_cache, "_versioned_context_key", fixed_context_key)
    monkeypatch.setattr(semantic_cache.redis_client, "get", fake_get)
    monkeypatch.setattr(semantic_cache, "embed_text", fixed_embedding)

    result = await semantic_cache.get_cached_answer(
        "user-1",
        "Dứa bị thối nõn xử lý thế nào?",
        None,
        "dứa",
    )

    assert result is None
    assert requested_keys == ["semcache_index:ctx"]


@pytest.mark.asyncio
async def test_cache_returns_answer_when_signature_and_vector_match(monkeypatch):
    question = "Dứa bị thối nõn do đâu?"

    async def fixed_context_key(*_args, **_kwargs):
        return "ctx"

    async def fake_get(key):
        if key == "semcache_index:ctx":
            return json.dumps([{
                "answer_key": "answer:cause",
                "vector": [1.0, 0.0],
                "question_signature": semantic_cache.question_signature(question),
            }])
        if key == "answer:cause":
            return json.dumps({"answer": "Nguyên nhân đã lưu"})
        return None

    async def fixed_embedding(_question):
        return [1.0, 0.0]

    monkeypatch.setattr(semantic_cache, "_versioned_context_key", fixed_context_key)
    monkeypatch.setattr(semantic_cache.redis_client, "get", fake_get)
    monkeypatch.setattr(semantic_cache, "embed_text", fixed_embedding)

    result = await semantic_cache.get_cached_answer(
        "user-1", question, None, "dứa"
    )

    assert result == {
        "answer": "Nguyên nhân đã lưu",
        "from_cache": True,
    }


@pytest.mark.asyncio
async def test_cache_rejects_legacy_entry_without_question_signature(monkeypatch):
    async def fixed_context_key(*_args, **_kwargs):
        return "ctx"

    async def fake_get(key):
        if key == "semcache_index:ctx":
            return json.dumps([{
                "answer_key": "answer:legacy",
                "vector": [1.0, 0.0],
            }])
        raise AssertionError("Legacy answer must not be loaded")

    async def fixed_embedding(_question):
        return [1.0, 0.0]

    monkeypatch.setattr(semantic_cache, "_versioned_context_key", fixed_context_key)
    monkeypatch.setattr(semantic_cache.redis_client, "get", fake_get)
    monkeypatch.setattr(semantic_cache, "embed_text", fixed_embedding)

    result = await semantic_cache.get_cached_answer(
        "user-1", "Dứa bị thối nõn do đâu?", None, "dứa"
    )

    assert result is None


@pytest.mark.asyncio
async def test_store_answer_indexes_question_signature(monkeypatch):
    question = "Dứa bị thối nõn do đâu?"
    writes = []

    async def fixed_context_key(*_args, **_kwargs):
        return "ctx"

    async def fake_get(_key):
        return None

    async def fake_set(key, value, **kwargs):
        writes.append((key, value, kwargs))

    async def fixed_embedding(_question):
        return [1.0, 0.0]

    monkeypatch.setattr(semantic_cache, "_versioned_context_key", fixed_context_key)
    monkeypatch.setattr(semantic_cache.redis_client, "get", fake_get)
    monkeypatch.setattr(semantic_cache.redis_client, "set", fake_set)
    monkeypatch.setattr(semantic_cache, "embed_text", fixed_embedding)

    await semantic_cache.store_answer(
        "user-1",
        question,
        None,
        "dứa",
        {"answer": "Nguyên nhân"},
    )

    index_write = next(
        value for key, value, _kwargs in writes if key == "semcache_index:ctx"
    )
    index = json.loads(index_write)
    assert index == [{
        "answer_key": index[0]["answer_key"],
        "vector": [1.0, 0.0],
        "question_signature": semantic_cache.question_signature(question),
    }]
    assert question not in index_write
