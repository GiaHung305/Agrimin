from app.api.chat import _provider_unavailable_response


def test_provider_unavailable_response_is_stable_and_safe():
    response = _provider_unavailable_response("conversation-1")
    assert response["guardrail_status"] == "block"
    assert response["confidence"] == 0.0
    assert response["citations"] == []
    assert response["conversation_id"] == "conversation-1"
