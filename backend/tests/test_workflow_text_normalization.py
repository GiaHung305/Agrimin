import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.workflow.text_normalization import normalize_workflow_text


def test_normalize_workflow_text_is_diacritic_and_whitespace_insensitive():
    assert normalize_workflow_text("  Đắk   Lắk\n") == "dak lak"
