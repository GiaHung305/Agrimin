import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from pydantic import ValidationError

from app.api.routes import documents
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


def test_storage_key_does_not_include_unicode_title_or_filename(monkeypatch):
    monkeypatch.setattr(documents.uuid, "uuid4", lambda: "document-id")

    assert documents._new_storage_key(".txt") == "documents/document-id.txt"
    assert documents._new_storage_key(".pdf") == "documents/document-id.pdf"


@pytest.mark.asyncio
async def test_ingest_failure_removes_newly_uploaded_object(monkeypatch):
    upload_file = AsyncMock()
    delete_file = AsyncMock()
    ingest_document = AsyncMock(side_effect=RuntimeError("embedding failed"))
    monkeypatch.setattr(documents, "upload_file", upload_file)
    monkeypatch.setattr(documents, "delete_file", delete_file)
    monkeypatch.setattr(documents, "ingest_document", ingest_document)
    monkeypatch.setattr(
        documents, "_new_storage_key", lambda _suffix: "documents/new.txt"
    )

    with pytest.raises(RuntimeError, match="embedding failed"):
        await documents.ingest(
            documents.IngestRequest(title="Document", content="Content"),
            db=SimpleNamespace(),
            current_user={"id": "admin"},
        )

    upload_file.assert_awaited_once()
    delete_file.assert_awaited_once_with("documents/new.txt")


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


@pytest.mark.asyncio
async def test_reclassify_commit_failure_restores_qdrant_payload(monkeypatch):
    document = SimpleNamespace(source_type="government")
    db = SimpleNamespace(
        execute=AsyncMock(return_value=ScalarResult(document)),
        commit=AsyncMock(side_effect=RuntimeError("commit failed")),
        rollback=AsyncMock(),
    )
    qdrant = SimpleNamespace(set_payload=AsyncMock())
    monkeypatch.setattr(documents, "qdrant_client", qdrant)

    with pytest.raises(RuntimeError, match="commit failed"):
        await documents.update_document_source_type(
            "document-1",
            documents.SourceTypeUpdate(source_type=SourceType.EXTENSION),
            db=db,
            current_user={"id": "admin"},
        )

    db.rollback.assert_awaited_once()
    assert qdrant.set_payload.await_count == 2
    assert qdrant.set_payload.await_args_list[0].kwargs["payload"] == {
        "source_type": "extension",
        "authority_score": 0.9,
    }
    assert qdrant.set_payload.await_args_list[1].kwargs["payload"] == {
        "source_type": "government",
        "authority_score": 0.95,
    }


@pytest.mark.asyncio
async def test_deactivate_commit_failure_restores_qdrant_active_flag(monkeypatch):
    document = SimpleNamespace(is_active=True)
    db = SimpleNamespace(
        execute=AsyncMock(return_value=ScalarResult(document)),
        commit=AsyncMock(side_effect=RuntimeError("commit failed")),
        rollback=AsyncMock(),
    )
    qdrant = SimpleNamespace(set_payload=AsyncMock())
    monkeypatch.setattr(documents, "qdrant_client", qdrant)

    with pytest.raises(RuntimeError, match="commit failed"):
        await documents.deactivate_document(
            "document-1", db=db, current_user={"id": "admin"}
        )

    db.rollback.assert_awaited_once()
    assert qdrant.set_payload.await_count == 2
    assert qdrant.set_payload.await_args_list[0].kwargs["payload"] == {
        "is_active": False
    }
    assert qdrant.set_payload.await_args_list[1].kwargs["payload"] == {
        "is_active": True
    }


@pytest.mark.asyncio
async def test_deactivate_inactive_document_never_reactivates_on_commit_failure(
    monkeypatch,
):
    document = SimpleNamespace(is_active=False)
    db = SimpleNamespace(
        execute=AsyncMock(return_value=ScalarResult(document)),
        commit=AsyncMock(side_effect=RuntimeError("commit failed")),
        rollback=AsyncMock(),
    )
    qdrant = SimpleNamespace(set_payload=AsyncMock())
    monkeypatch.setattr(documents, "qdrant_client", qdrant)

    with pytest.raises(RuntimeError, match="commit failed"):
        await documents.deactivate_document(
            "document-1", db=db, current_user={"id": "admin"}
        )

    assert qdrant.set_payload.await_count == 2
    assert qdrant.set_payload.await_args_list[1].kwargs["payload"] == {
        "is_active": False
    }


@pytest.mark.asyncio
async def test_admin_can_purge_document_from_all_backends(monkeypatch):
    document = SimpleNamespace(
        id="document-1",
        file_key="documents/source.pdf",
        is_active=True,
    )
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[ScalarResult(document), SimpleNamespace(), SimpleNamespace()]
        ),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    qdrant = SimpleNamespace(delete=AsyncMock(), set_payload=AsyncMock())
    delete_file = AsyncMock()
    bump_cache = AsyncMock()
    monkeypatch.setattr(documents, "qdrant_client", qdrant)
    monkeypatch.setattr(documents, "delete_file", delete_file)
    monkeypatch.setattr(
        documents, "bump_semantic_cache_corpus_version", bump_cache
    )
    monkeypatch.setattr(documents, "invalidate_bm25_index", lambda: None)

    response = await documents.purge_document(
        "document-1", db=db, current_user={"id": "admin"}
    )

    assert response == {"status": "purged", "document_id": "document-1"}
    qdrant.set_payload.assert_awaited_once()
    qdrant.delete.assert_awaited_once()
    delete_file.assert_awaited_once_with("documents/source.pdf")
    assert db.execute.await_count == 3
    assert db.commit.await_count == 2
    db.rollback.assert_not_awaited()
    bump_cache.assert_awaited_once()


@pytest.mark.asyncio
async def test_purge_cleanup_failure_leaves_retryable_inactive_tombstone(
    monkeypatch,
):
    document = SimpleNamespace(
        id="document-1",
        file_key="documents/source.pdf",
        is_active=True,
    )
    db = SimpleNamespace(
        execute=AsyncMock(return_value=ScalarResult(document)),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    qdrant = SimpleNamespace(delete=AsyncMock(), set_payload=AsyncMock())
    delete_file = AsyncMock(side_effect=RuntimeError("storage unavailable"))
    bump_cache = AsyncMock()
    monkeypatch.setattr(documents, "qdrant_client", qdrant)
    monkeypatch.setattr(documents, "delete_file", delete_file)
    monkeypatch.setattr(
        documents, "bump_semantic_cache_corpus_version", bump_cache
    )
    monkeypatch.setattr(documents, "invalidate_bm25_index", lambda: None)

    with pytest.raises(RuntimeError, match="storage unavailable"):
        await documents.purge_document(
            "document-1", db=db, current_user={"id": "admin"}
        )

    assert document.is_active is False
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()
    assert db.execute.await_count == 1
    qdrant.set_payload.assert_awaited_once()
    qdrant.delete.assert_awaited_once()
    bump_cache.assert_awaited_once()


@pytest.mark.asyncio
async def test_purge_database_delete_failure_rolls_back_inactive_tombstone(
    monkeypatch,
):
    document = SimpleNamespace(
        id="document-1",
        file_key="documents/source.pdf",
        is_active=True,
    )
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[ScalarResult(document), SimpleNamespace(), SimpleNamespace()]
        ),
        commit=AsyncMock(
            side_effect=[None, RuntimeError("database delete failed")]
        ),
        rollback=AsyncMock(),
    )
    qdrant = SimpleNamespace(delete=AsyncMock(), set_payload=AsyncMock())
    delete_file = AsyncMock()
    monkeypatch.setattr(documents, "qdrant_client", qdrant)
    monkeypatch.setattr(documents, "delete_file", delete_file)
    monkeypatch.setattr(
        documents, "bump_semantic_cache_corpus_version", AsyncMock()
    )
    monkeypatch.setattr(documents, "invalidate_bm25_index", lambda: None)

    with pytest.raises(RuntimeError, match="database delete failed"):
        await documents.purge_document(
            "document-1", db=db, current_user={"id": "admin"}
        )

    assert document.is_active is False
    assert db.commit.await_count == 2
    db.rollback.assert_awaited_once()
    qdrant.delete.assert_awaited_once()
    delete_file.assert_awaited_once()
