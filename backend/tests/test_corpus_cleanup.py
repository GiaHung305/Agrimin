import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eval.apply_corpus_cleanup import load_manifest, validate_document


def _entry() -> dict[str, str]:
    return {
        "id": "17ab0a40-7a1b-4a41-86fc-242dc5198720",
        "title": "Sample",
        "source": "Test",
        "category": "test_data",
        "reason": "Not production evidence",
    }


def test_cleanup_manifest_requires_soft_deactivation_and_unique_ids(tmp_path: Path):
    entry = _entry()
    manifest = {
        "action": "soft_deactivate",
        "documents": [entry, dict(entry)],
    }
    path = tmp_path / "cleanup.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate_document_id"):
        load_manifest(path)


def test_cleanup_rejects_metadata_drift_before_mutation():
    entry = _entry()
    document = SimpleNamespace(
        id=entry["id"], title="Different", source=entry["source"]
    )

    with pytest.raises(ValueError, match="title_mismatch"):
        validate_document(entry, document)
