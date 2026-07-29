import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.retrieval.chunking import chunk_text


def test_chunk_empty_text():
    """Input rỗng phải trả về danh sách rỗng, không crash."""
    result = chunk_text("")
    assert result == []


def test_chunk_short_text():
    """Text ngắn hơn chunk_size phải trả về đúng 1 chunk."""
    text = "Đây là một câu ngắn."
    result = chunk_text(text, chunk_size=500)
    assert len(result) == 1
    assert result[0] == text


def test_chunk_long_text_produces_multiple_chunks():
    """Text dài hơn chunk_size phải được chia thành nhiều chunk."""
    text = " ".join(["từ"] * 1000)  # 1000 từ
    result = chunk_text(text, chunk_size=500, overlap=50)
    assert len(result) > 1


def test_chunk_overlap_preserved():
    """Các chunk liên tiếp phải có phần chồng lấn (overlap) đúng như tham số."""
    text = " ".join([str(i) for i in range(100)])
    result = chunk_text(text, chunk_size=50, overlap=10)
    assert len(result) >= 2
    # Từ cuối của chunk đầu phải xuất hiện trong chunk thứ 2 (do overlap)
    first_chunk_words = result[0].split()
    second_chunk_words = result[1].split()
    assert first_chunk_words[-1] in second_chunk_words