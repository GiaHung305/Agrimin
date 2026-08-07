import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

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
