import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.retrieval.text_normalization import normalize_vietnamese, tokenize_vietnamese


def test_vietnamese_normalization_matches_accented_and_ascii_text():
    assert normalize_vietnamese("Sầu riêng ở Đắk Lắk") == "sau rieng o dak lak"


def test_tokenizer_keeps_agricultural_numbers_and_units_searchable():
    assert tokenize_vietnamese("Pha 20 ml, nồng độ 0,5%") == [
        "pha",
        "20",
        "ml",
        "nong",
        "do",
        "0,5%",
    ]
