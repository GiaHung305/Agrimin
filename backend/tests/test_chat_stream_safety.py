import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.api.chat import _approved_answer_chunks


def test_approved_answer_chunks_preserve_matching_generation():
    chunks = _approved_answer_chunks(
        "Câu trả lời.\n\n(Lưu ý an toàn)",
        ["Câu ", "trả lời."],
    )

    assert chunks == ["Câu ", "trả lời.", "\n\n(Lưu ý an toàn)"]
    assert "".join(chunks) == "Câu trả lời.\n\n(Lưu ý an toàn)"


def test_approved_answer_chunks_discards_guardrail_rejected_draft():
    chunks = _approved_answer_chunks(
        "Tôi chưa tìm đủ thông tin để trả lời chắc chắn.",
        ["Nội dung nháp ", "không được duyệt."],
    )

    assert chunks == ["Tôi chưa tìm đủ thông tin để trả lời chắc chắn."]


def test_approved_answer_chunks_handles_buffered_high_risk_answer():
    assert _approved_answer_chunks("Nội dung đã được duyệt.", []) == [
        "Nội dung đã được duyệt."
    ]
