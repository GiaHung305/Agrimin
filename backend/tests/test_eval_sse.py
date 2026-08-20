import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eval import run_eval
from eval.run_eval import citation_matches, parse_sse_response
from app.services import model_gateway
from app.services.model_gateway import ModelProviderUnavailable


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


def test_traceable_citation_match_rejects_title_only_or_inactive_evidence():
    title_only = [{"title": "Khuyến nông Việt Nam"}]
    inactive = [{
        "title": "Khuyến nông Việt Nam",
        "document_id": "doc-1",
        "chunk_id": "chunk-1",
        "is_active": False,
    }]
    active = [{**inactive[0], "is_active": True}]

    assert not citation_matches(
        "Khuyến nông", title_only, require_traceable=True
    )
    assert not citation_matches(
        "Khuyến nông", inactive, require_traceable=True
    )
    assert citation_matches("Khuyến nông", active, require_traceable=True)


@pytest.mark.asyncio
async def test_eval_import_does_not_require_api_key(monkeypatch):
    monkeypatch.setattr(model_gateway, "client", None)
    monkeypatch.setattr(model_gateway.settings, "google_api_key", "")

    with pytest.raises(ModelProviderUnavailable, match="API key is not configured"):
        await run_eval.llm_judge("expected", "actual")
