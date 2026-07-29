import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.retrieval.fusion import reciprocal_rank_fusion


def test_fusion_empty_inputs():
    """Cả 2 danh sách rỗng phải trả về rỗng, không crash."""
    result = reciprocal_rank_fusion([], [])
    assert result == []


def test_fusion_prioritizes_docs_in_both_lists():
    """Document xuất hiện ở cả dense và bm25 phải được xếp cao hơn document chỉ có ở 1 nguồn."""
    dense_results = [
        {"content": "Tài liệu A về tưới nước cà chua"},
        {"content": "Tài liệu B về đất trồng"},
    ]
    bm25_results = [
        {"content": "Tài liệu A về tưới nước cà chua"},
        {"content": "Tài liệu C về sâu bệnh"},
    ]
    result = reciprocal_rank_fusion(dense_results, bm25_results)

    assert len(result) == 3
    # Tài liệu A xuất hiện ở cả 2 nguồn, phải đứng đầu
    assert result[0]["content"] == "Tài liệu A về tưới nước cà chua"


def test_fusion_single_source_only():
    """Chỉ có dense_results, không có bm25 — vẫn phải hoạt động."""
    dense_results = [{"content": "Chỉ có trong dense"}]
    result = reciprocal_rank_fusion(dense_results, [])
    assert len(result) == 1