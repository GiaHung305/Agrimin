import os
import sys
import json

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eval.run_retrieval_eval import (
    DEFAULT_BASELINE,
    DEFAULT_DATASET,
    evaluate,
    evaluate_promotion_gate,
    is_relevant,
    retrieval_metrics,
)


def test_default_retrieval_gate_uses_real_production_sources():
    dataset = json.loads(DEFAULT_DATASET.read_text(encoding="utf-8"))
    baseline = json.loads(DEFAULT_BASELINE.read_text(encoding="utf-8"))
    serialized = json.dumps(dataset, ensure_ascii=False).casefold()

    assert dataset["version"] == baseline["dataset_version"]
    assert "tai lieu mau" not in serialized
    assert "tài liệu mẫu" not in serialized
    assert "pdf mau" not in serialized


def test_retrieval_metrics_reward_early_relevant_result():
    metrics = retrieval_metrics([False, True, False])
    assert metrics["recall_at_1"] == 0.0
    assert metrics["recall_at_k"] == 1.0
    assert metrics["mrr"] == 0.5
    assert 0 < metrics["ndcg_at_k"] < 1


def test_retrieval_metrics_handle_complete_miss():
    assert retrieval_metrics([False, False]) == {
        "recall_at_1": 0.0,
        "recall_at_k": 0.0,
        "mrr": 0.0,
        "ndcg_at_k": 0.0,
    }


def test_relevance_matches_source_case_insensitively():
    result = {"source": "Tai Lieu PDF Mau", "title": "Khác"}
    assert is_relevant(result, ["tai lieu pdf mau"])


def test_relevance_accepts_traceable_title_fragment():
    result = {"title": "Quy trinh quan ly benh Greening tren cay co mui"}
    assert is_relevant(result, ["benh Greening"])


def test_promotion_gate_rejects_quality_regression():
    gate = evaluate_promotion_gate(
        {
            "recall_at_1": 0.5,
            "recall_at_k": 1.0,
            "mrr": 0.5,
            "ndcg_at_k": 0.7,
            "mean_latency_ms": 1000,
        },
        {
            "minimum_recall_at_1": 0.7,
            "minimum_recall_at_k": 0.9,
            "minimum_mrr": 0.8,
            "minimum_ndcg_at_k": 0.8,
            "maximum_mean_latency_ms": 30000,
        },
    )
    assert gate["passed"] is False
    assert gate["checks"]["recall_at_1"] is False
    assert gate["checks"]["mrr"] is False


@pytest.mark.asyncio
async def test_evaluate_reads_agriculture_case_schema(monkeypatch, tmp_path):
    dataset = tmp_path / "agriculture.json"
    dataset.write_text(
        """{
          "version": "agriculture-test",
          "cases": [
            {
              "id": "normal",
              "category": "plant_disease",
              "question": "Benh tren cay?",
              "expected_citations_any": ["Quy trinh benh cay"]
            },
            {
              "id": "unsafe",
              "category": "safety",
              "question": "Pha thuoc?",
              "expected_citations_any": []
            }
          ]
        }""",
        encoding="utf-8",
    )

    async def search(query, top_k):
        assert query == "Benh tren cay?"
        assert top_k == 3
        return [{"title": "Quy trinh benh cay chinh thuc"}]

    monkeypatch.setattr("eval.run_retrieval_eval.hybrid_search", search)

    result = await evaluate(dataset, top_k=3)

    assert result["dataset_version"] == "agriculture-test"
    assert len(result["items"]) == 1
    assert result["aggregate"]["recall_at_1"] == 1.0
