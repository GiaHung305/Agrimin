import os
import sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.retrieval.evidence import citation_from_evidence, normalize_evidence
from app.services import ingest_service
from app.retrieval.source_authority import (
    authority_score,
    supports_high_risk,
    supports_numeric_dosage,
)
from eval.migrate_qdrant_source_authority import metadata_for_payload


def test_source_authority_policy_is_conservative_for_unknown_uploads():
    assert authority_score("unknown") == 0.2
    assert not supports_high_risk("user_upload")
    assert not supports_numeric_dosage("research")


def test_manufacturer_label_can_support_numeric_dosage():
    assert supports_high_risk("manufacturer_label")
    assert supports_numeric_dosage("manufacturer_label")


def test_evidence_and_citation_preserve_source_authority():
    evidence = normalize_evidence(
        {
            "document_id": "d1",
            "chunk_id": "c1",
            "content": "label",
            "source_type": "manufacturer_label",
            "published_date": "2025-01-02T00:00:00+00:00",
        }
    )
    citation = citation_from_evidence(evidence)
    assert evidence["authority_score"] == 0.9
    assert citation["source_type"] == "manufacturer_label"
    assert citation["authority_score"] == 0.9
    assert citation["published_date"] == "2025-01-02T00:00:00+00:00"


def test_qdrant_backfill_prefers_relational_document_type():
    published = datetime(2024, 8, 13)
    metadata = metadata_for_payload(
        {"document_id": "d1", "source_type": "unknown"},
        {
            "d1": {
                "source_type": "extension",
                "published_date": published,
            }
        },
    )
    assert metadata == {
        "source_type": "extension",
        "authority_score": 0.9,
        "published_date": "2024-08-13T00:00:00",
    }


@pytest.mark.asyncio
async def test_published_date_update_keeps_qdrant_and_cache_in_sync(monkeypatch):
    published = datetime(2025, 1, 2)
    document = SimpleNamespace(id="d1", published_date=None)
    db = SimpleNamespace(commit=AsyncMock())
    qdrant = SimpleNamespace(set_payload=AsyncMock())
    invalidate = Mock()
    bump_cache = AsyncMock()
    monkeypatch.setattr(ingest_service, "qdrant_client", qdrant)
    monkeypatch.setattr(ingest_service, "invalidate_bm25_index", invalidate)
    monkeypatch.setattr(
        ingest_service, "bump_semantic_cache_corpus_version", bump_cache
    )

    await ingest_service.update_document_published_date(
        db, document, published
    )

    assert document.published_date == published
    assert qdrant.set_payload.await_args.kwargs["payload"] == {
        "published_date": "2025-01-02T00:00:00"
    }
    db.commit.assert_awaited_once()
    invalidate.assert_called_once()
    bump_cache.assert_awaited_once()
