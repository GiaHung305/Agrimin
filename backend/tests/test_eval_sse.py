import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eval import run_eval
from eval.run_eval import citation_matches, parse_sse_response


def test_parse_sse_response_handles_event_delimiters():
    raw = (
        'data: {"type":"chunk","payload":"Xin "}\r\n\r\n'
        'data: {"type":"chunk","payload":"chào"}\r\n\r\n'
        'data: {"type":"meta","payload":{"guardrail_status":"pass",'
        '"citations":[{"title":"Khuyến nông","document_id":"d1","chunk_id":"c1"}]}}\r\n\r\n'
        'data: {"type":"done"}\r\n\r\n'
    )
    result = parse_sse_response(raw)
    assert result["answer"] == "Xin chào"
    assert result["guardrail_status"] == "pass"


def test_citation_match_supports_evidence_objects():
    citations = [{"title": "Tài liệu mẫu", "document_id": "d1", "chunk_id": "c1"}]
    assert citation_matches("Tài liệu mẫu", citations)


def test_eval_import_does_not_require_api_key(monkeypatch):
    monkeypatch.setattr(run_eval, "judge_client", None)
    monkeypatch.setattr(run_eval.settings, "google_api_key", "")

    with pytest.raises(RuntimeError, match="GOOGLE_API_KEY is required"):
        run_eval._get_judge_client()
