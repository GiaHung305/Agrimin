import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.workflow.measurements import extract_numeric_measurements


def test_measurements_normalize_vietnamese_aliases_and_rates():
    claims = extract_numeric_measurements(
        "Pha 20 cc cho bình 16 lít; lượng dùng 2,5 kg/ha."
    )

    assert ("20", "ml") in claims
    assert ("16", "l") in claims
    assert ("2.5", "kg/ha") in claims


def test_measurements_extract_dilution_ratio():
    assert ("1:100", "ratio") in extract_numeric_measurements(
        "Pha theo tỷ lệ 1 : 100."
    )
