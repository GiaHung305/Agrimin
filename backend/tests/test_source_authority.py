import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.retrieval.evidence import citation_from_evidence, normalize_evidence
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
        }
    )
    citation = citation_from_evidence(evidence)
    assert evidence["authority_score"] == 0.9
    assert citation["source_type"] == "manufacturer_label"
    assert citation["authority_score"] == 0.9


def test_qdrant_backfill_prefers_relational_document_type():
    metadata = metadata_for_payload(
        {"document_id": "d1", "source_type": "unknown"},
        {"d1": "extension"},
    )
    assert metadata == {"source_type": "extension", "authority_score": 0.9}
