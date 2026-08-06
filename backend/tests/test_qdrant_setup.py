import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from qdrant_client.models import PayloadSchemaType

from app.retrieval import qdrant_setup


class FakeQdrant:
    def __init__(self):
        self.created_collection = False
        self.indexes = []

    async def get_collections(self):
        return SimpleNamespace(collections=[])

    async def create_collection(self, **kwargs):
        self.created_collection = True

    async def create_payload_index(self, **kwargs):
        self.indexes.append(kwargs)


@pytest.mark.asyncio
async def test_setup_creates_filter_indexes(monkeypatch):
    client = FakeQdrant()
    monkeypatch.setattr(qdrant_setup, "qdrant_client", client)

    await qdrant_setup.ensure_collection_exists()

    assert client.created_collection
    schemas = {item["field_name"]: item["field_schema"] for item in client.indexes}
    assert schemas == {
        "is_active": PayloadSchemaType.BOOL,
        "document_id": PayloadSchemaType.KEYWORD,
    }
