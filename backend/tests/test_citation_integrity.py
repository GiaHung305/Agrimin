import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.workflow.citation_integrity import (
    prune_exact_rejected_claims,
    prune_rejected_claim_ids,
    prune_uncited_technical_claims,
    referenced_evidence_indexes,
    technical_claim_units,
    uncited_technical_claims,
)


def test_referenced_evidence_indexes_preserve_first_claim_order():
    assert referenced_evidence_indexes(
        "Nguồn thứ hai [E2], rồi nguồn thứ nhất [E1], lặp lại [E2]."
    ) == [2, 1]


@pytest.mark.parametrize("separator", ["", " "])
def test_marker_after_period_does_not_cover_following_claim(separator):
    answer = (
        f"Đất cần thoát nước tốt.{separator}[E1] "
        "Nên phun thuốc ngay khi thấy lá vàng."
    )

    assert uncited_technical_claims(answer) == [
        "Nên phun thuốc ngay khi thấy lá vàng."
    ]


def test_detects_uncited_technical_claim_after_a_cited_claim():
    answer = (
        "Thoát nước giúp hạn chế úng [E1]. "
        "Bón thêm đạm để cây phục hồi nhanh."
    )

    assert uncited_technical_claims(answer) == [
        "Bón thêm đạm để cây phục hồi nhanh."
    ]


def test_marker_after_period_stays_attached_to_the_preceding_claim():
    assert uncited_technical_claims(
        "Theo nhãn, pha 20 ml cho bình 16 lít. [E1]"
    ) == []


def test_headings_questions_and_uncertainty_limits_do_not_need_citations():
    answer = """Cách xử lý:
Chưa đủ bằng chứng để khuyến nghị phun thuốc.
Bạn có thể gửi thêm ảnh hai mặt lá?
"""

    assert uncited_technical_claims(answer) == []


@pytest.mark.parametrize(
    "answer",
    [
        (
            "Để cà rốt phát triển tốt và đạt năng suất cao, mình chia sẻ với "
            "bạn hai yếu tố cực kỳ quan trọng về đất đai và nguyên tắc quản lý "
            "sâu bệnh như sau:"
        ),
        (
            "Để giúp bạn chủ động bảo vệ vườn tiêu, mình xin chia sẻ chi tiết "
            "về nguyên nhân, cách phân biệt và các biện pháp phòng ngừa nền "
            "tảng cho hai bệnh này:"
        ),
        (
            "Để cà rốt phát triển tốt và cho củ đẹp, bạn cần chú ý chuẩn bị "
            "đất trồng thật kỹ và tuân thủ các nguyên tắc quản lý sâu bệnh "
            "sau đây:"
        ),
        (
            "Để giúp bạn giữ cam và bưởi tươi ngon, mình đã chuẩn bị quy trình "
            "xử lý chi tiết dưới đây:"
        ),
        (
            "Để giúp bạn xác định tình trạng vườn, mình cần bạn kiểm tra các "
            "yếu tố sau:"
        ),
        "Dưới đây là cách xử lý cụ thể bạn cần thực hiện ngay:",
    ],
)
def test_response_framing_that_only_introduces_a_list_needs_no_citation(answer):
    assert uncited_technical_claims(answer) == []


def test_response_framing_does_not_exempt_a_following_uncited_directive():
    answer = (
        "Để xử lý bệnh, mình chia sẻ như sau: "
        "Nên phun thuốc ngay khi thấy lá vàng."
    )

    assert uncited_technical_claims(answer) == [
        "Để xử lý bệnh, mình chia sẻ như sau: Nên phun thuốc ngay khi thấy lá vàng."
    ]


def test_markdown_heading_and_scientific_abbreviation_are_not_claims():
    answer = """**Nguyên nhân chính gây bệnh chết nhanh:**
Bệnh chủ yếu do nấm *Phytophthora* spp. gây thối rễ [E1].
"""

    assert uncited_technical_claims(answer) == []


def test_prune_removes_only_residual_uncited_technical_sentences():
    answer = """**Cách xử lý:**
Thoát nước để hạn chế úng [E1]. Nên phun thuốc ngay khi thấy lá vàng.
Bạn theo dõi thêm trong vài ngày.
"""

    pruned, removed = prune_uncited_technical_claims(answer)

    assert removed == ["Nên phun thuốc ngay khi thấy lá vàng."]
    assert "Thoát nước để hạn chế úng [E1]." in pruned
    assert "Bạn theo dõi thêm trong vài ngày." in pruned
    assert "Nên phun thuốc" not in pruned
    assert uncited_technical_claims(pruned) == []


def test_prune_exact_rejected_claim_removes_only_copied_sentence():
    answer = (
        "Thoát nước để hạn chế úng [E1]. "
        "Không tưới Cytosinpeptidemycin vào nõn [E2]."
    )

    pruned, removed = prune_exact_rejected_claims(
        answer,
        ["Không tưới Cytosinpeptidemycin vào nõn [E2]."],
    )

    assert removed == ["Không tưới Cytosinpeptidemycin vào nõn [E2]."]
    assert pruned == "Thoát nước để hạn chế úng [E1]."


def test_prune_exact_rejected_claim_never_accepts_paraphrase_or_substring():
    answer = "Không tưới Cytosinpeptidemycin vào nõn khi trời mưa [E2]."

    pruned, removed = prune_exact_rejected_claims(
        answer,
        ["Không tưới hoạt chất này vào nõn."],
    )

    assert removed == []
    assert pruned == answer


def test_numbered_technical_claims_prune_by_stable_id_only():
    answer = (
        "Cách xử lý:\n"
        "- Thoát nước để hạn chế úng [E1]. "
        "Bón thêm đạm để cây hồi phục [E2].\n"
        "Bạn có thể gửi thêm ảnh?"
    )

    assert technical_claim_units(answer) == [
        "Thoát nước để hạn chế úng [E1].",
        "Bón thêm đạm để cây hồi phục [E2].",
    ]

    pruned, removed = prune_rejected_claim_ids(answer, [2])

    assert removed == ["Bón thêm đạm để cây hồi phục [E2]."]
    assert "Thoát nước để hạn chế úng [E1]." in pruned
    assert "Bón thêm đạm" not in pruned
    assert "Bạn có thể gửi thêm ảnh?" in pruned


def test_numbered_claims_include_cited_fact_without_keyword_match():
    answer = (
        "Khi kéo nhẹ, lá non tuột khỏi thân và có mùi khó chịu [E1]. "
        "Bạn có thể gửi thêm ảnh?"
    )

    assert technical_claim_units(answer) == [
        "Khi kéo nhẹ, lá non tuột khỏi thân và có mùi khó chịu [E1]."
    ]


def test_prune_rejected_claim_ids_ignores_invalid_ids():
    answer = "Thoát nước để hạn chế úng [E1]."

    pruned, removed = prune_rejected_claim_ids(answer, [0, 2, -1])

    assert removed == []
    assert pruned == answer


def test_direct_visual_observation_is_not_forced_to_cite_rag():
    answer = (
        "Quan sát trực tiếp trong ảnh: lá có vùng vàng ở mép. "
        "Dấu hiệu này có thể liên quan bệnh thối nõn [E1]."
    )

    assert uncited_technical_claims(answer) == []
