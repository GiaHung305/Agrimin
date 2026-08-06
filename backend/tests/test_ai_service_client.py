import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.core import ai_service_client


class FakeClient:
    def __init__(self):
        self.is_closed = False
        self.closed = False

    async def aclose(self):
        self.closed = True
        self.is_closed = True


@pytest.mark.asyncio
async def test_ai_service_client_reuses_and_closes_pool(monkeypatch):
    created = []

    def make_client(**kwargs):
        client = FakeClient()
        created.append(client)
        return client

    await ai_service_client.close_ai_service_client()
    monkeypatch.setattr(ai_service_client.httpx, "AsyncClient", make_client)

    first = ai_service_client.get_ai_service_client()
    second = ai_service_client.get_ai_service_client()
    assert first is second
    assert len(created) == 1

    await ai_service_client.close_ai_service_client()
    assert first.closed
