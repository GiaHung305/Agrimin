import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.tools.mcp_weather_client import MCPToolResponseError, extract_structured_content


def test_extracts_current_camel_case_sdk_shape():
    result = SimpleNamespace(structuredContent={"found": True})
    assert extract_structured_content(result) == {"found": True}


def test_extracts_legacy_snake_case_sdk_shape():
    result = SimpleNamespace(structured_content={"forecast": []})
    assert extract_structured_content(result) == {"forecast": []}


def test_extracts_json_text_fallback():
    result = SimpleNamespace(
        structuredContent=None,
        content=[SimpleNamespace(text='{"found": false}')],
    )
    assert extract_structured_content(result) == {"found": False}


def test_rejects_malformed_tool_result():
    result = SimpleNamespace(structuredContent=None, content=[])
    with pytest.raises(MCPToolResponseError):
        extract_structured_content(result)
