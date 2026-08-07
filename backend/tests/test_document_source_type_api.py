import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from pydantic import ValidationError

from app.api import documents
from app.retrieval.source_authority import SourceType


class ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


def test_ingest_request_rejects_unknown_taxonomy_value():
    with pytest.raises(ValidationError):
        documents.IngestRequest(
            title="Document",
            content="Content",
            source_type="blog",
        )


@pytest.mark.asyncio
async def test_admin_can_reclassify_document_and_qdrant_payload(monkeypatch):
    document = SimpleNamespace(source_type="unknown")
    db = SimpleNamespace(
        execute=AsyncMock(return_value=ScalarResult(document)),
        commit=AsyncMock(),
    )
    qdrant = SimpleNamespace(set_payload=AsyncMock())
    monkeypatch.setattr(documents, "qdrant_client", qdrant)
    monkeypatch.setattr(documents, "invalidate_bm25_index", lambda: None)

    response = await documents.update_document_source_type(
        "document-1",
        documents.SourceTypeUpdate(source_type=SourceType.EXTENSION),
        db=db,
        current_user={"id": "admin"},
    )

    assert document.source_type == "extension"
    db.commit.assert_awaited_once()
    qdrant.set_payload.assert_awaited_once()
    assert response["authority_score"] == 0.9
