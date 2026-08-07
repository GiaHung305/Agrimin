import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eval.run_retrieval_eval import (
    evaluate_promotion_gate,
    is_relevant,
    retrieval_metrics,
)


def test_retrieval_metrics_reward_early_relevant_result():
    metrics = retrieval_metrics([False, True, False])
    assert metrics["recall_at_k"] == 1.0
    assert metrics["mrr"] == 0.5
    assert 0 < metrics["ndcg_at_k"] < 1


def test_retrieval_metrics_handle_complete_miss():
    assert retrieval_metrics([False, False]) == {
        "recall_at_k": 0.0,
        "mrr": 0.0,
        "ndcg_at_k": 0.0,
    }


def test_relevance_matches_source_case_insensitively():
    result = {"source": "Tai Lieu PDF Mau", "title": "Khác"}
    assert is_relevant(result, ["tai lieu pdf mau"])


def test_promotion_gate_rejects_quality_regression():
    gate = evaluate_promotion_gate(
        {
            "recall_at_k": 1.0,
            "mrr": 0.5,
            "ndcg_at_k": 0.7,
            "mean_latency_ms": 1000,
        },
        {
            "minimum_recall_at_k": 0.9,
            "minimum_mrr": 0.8,
            "minimum_ndcg_at_k": 0.8,
            "maximum_mean_latency_ms": 30000,
        },
    )
    assert gate["passed"] is False
    assert gate["checks"]["mrr"] is False
