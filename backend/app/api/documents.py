import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_admin
from app.core.config import settings
from app.core.db import get_db
from app.core.qdrant_client import qdrant_client
from app.repository.models import Document, DocumentChunk
from app.retrieval.qdrant_setup import COLLECTION_NAME
from app.retrieval.bm25_search import invalidate_bm25_index
from app.services.ingest_service import ingest_document
from app.services.pdf_extractor import extract_text_from_pdf
from app.services.storage_service import delete_file, upload_file
from app.services.semantic_cache import bump_semantic_cache_corpus_version
from app.retrieval.source_authority import SourceType, authority_score

router = APIRouter(tags=["documents"])
logger = logging.getLogger(__name__)


def _new_storage_key(suffix: str) -> str:
    """Create an object key independent of untrusted display metadata."""
    return f"documents/{uuid.uuid4()}{suffix}"


async def _cleanup_failed_upload(file_key: str) -> None:
    """Best-effort compensation when storage succeeds but ingestion fails."""
    try:
        await delete_file(file_key)
    except Exception:
        logger.error(
            "Failed to remove uploaded document after ingestion error",
            extra={"file_key": file_key},
            exc_info=True,
        )


async def _restore_qdrant_payload(
    document_id: str, payload: dict[str, object]
) -> None:
    """Best-effort restore without masking the original database error."""
    try:
        await qdrant_client.set_payload(
            collection_name=COLLECTION_NAME,
            payload=payload,
            points=Filter(
                must=[
                    FieldCondition(
                        key="document_id", match=MatchValue(value=document_id)
                    )
                ]
            ),
            wait=True,
        )
    except Exception:
        logger.error(
            "Failed to restore Qdrant document metadata",
            extra={"document_id": document_id},
            exc_info=True,
        )


async def _deactivate_for_retrieval(
    db: AsyncSession, document: Document, document_id: str
) -> None:
    """Commit an inactive tombstone before any destructive external cleanup."""
    previous_active = bool(document.is_active)
    qdrant_updated = False
    try:
        await qdrant_client.set_payload(
            collection_name=COLLECTION_NAME,
            payload={"is_active": False},
            points=Filter(
                must=[
                    FieldCondition(
                        key="document_id", match=MatchValue(value=document_id)
                    )
                ]
            ),
            wait=True,
        )
        qdrant_updated = True
        document.is_active = False
        await db.commit()
    except Exception:
        await db.rollback()
        if qdrant_updated:
            await _restore_qdrant_payload(
                document_id, {"is_active": previous_active}
            )
        raise
    invalidate_bm25_index()
    await bump_semantic_cache_corpus_version()


class IngestRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=1_000_000)
    source: str | None = Field(default=None, max_length=255)
    source_type: SourceType = SourceType.UNKNOWN
    author: str | None = Field(default=None, max_length=255)
    version: str | None = Field(default=None, max_length=50)


class SourceTypeUpdate(BaseModel):
    source_type: SourceType


@router.post("/documents/ingest")
async def ingest(
    req: IngestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    file_key = _new_storage_key(".txt")
    await upload_file(req.content.encode("utf-8"), file_key, content_type="text/plain")

    try:
        document = await ingest_document(
            db=db,
            title=req.title,
            content=req.content,
            source=req.source,
            source_type=req.source_type,
            author=req.author,
            version=req.version,
            file_key=file_key,
        )
    except Exception:
        await _cleanup_failed_upload(file_key)
        raise
    return {"document_id": str(document.id), "title": document.title, "file_key": file_key}


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(..., min_length=1, max_length=500),
    source: str | None = Form(None, max_length=255),
    source_type: SourceType = Form(SourceType.UNKNOWN),
    author: str | None = Form(None, max_length=255),
    version: str | None = Form(None, max_length=50),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Only PDF files are supported")

    file_bytes = await file.read(settings.max_upload_bytes + 1)
    if len(file_bytes) > settings.max_upload_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Uploaded file is too large")
    if not file_bytes.startswith(b"%PDF-"):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Invalid PDF file")

    try:
        content = extract_text_from_pdf(file_bytes)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unable to parse PDF") from exc

    if not content.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No extractable text found in PDF")
    if len(content) > 1_000_000:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Extracted document text is too large")

    file_key = _new_storage_key(".pdf")
    await upload_file(file_bytes, file_key, content_type="application/pdf")

    try:
        document = await ingest_document(
            db=db,
            title=title,
            content=content,
            source=source,
            source_type=source_type,
            author=author,
            version=version,
            file_key=file_key,
        )
    except Exception:
        await _cleanup_failed_upload(file_key)
        raise
    return {
        "document_id": str(document.id),
        "title": document.title,
        "extracted_chars": len(content),
        "file_key": file_key,
    }


@router.get("/documents")
async def list_documents(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    result = await db.execute(select(Document).order_by(Document.ingested_at.desc()))
    docs = result.scalars().all()
    return [
        {
            "id": str(document.id),
            "title": document.title,
            "source": document.source,
            "source_type": document.source_type,
            "authority_score": authority_score(document.source_type),
            "version": document.version,
            "published_date": (
                document.published_date.isoformat()
                if document.published_date
                else None
            ),
            "is_active": document.is_active,
            "ingested_at": document.ingested_at.isoformat(),
            "file_key": document.file_key,
        }
        for document in docs
    ]


@router.patch("/documents/{document_id}/deactivate")
async def deactivate_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    await _deactivate_for_retrieval(db, document, document_id)
    return {"status": "deactivated", "document_id": document_id}


@router.delete("/documents/{document_id}")
async def purge_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """Permanently purge one document from storage, retrieval, and Postgres."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    # Persist a safe, retryable tombstone first. If any cleanup below fails,
    # the document remains inactive and a later DELETE can continue idempotently.
    await _deactivate_for_retrieval(db, document, document_id)
    await qdrant_client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=FilterSelector(
            filter=Filter(
                must=[
                    FieldCondition(
                        key="document_id", match=MatchValue(value=document_id)
                    )
                ]
            )
        ),
        wait=True,
    )
    if document.file_key:
        await delete_file(document.file_key)
    try:
        await db.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document.id)
        )
        await db.execute(delete(Document).where(Document.id == document.id))
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return {"status": "purged", "document_id": document_id}


@router.patch("/documents/{document_id}/source-type")
async def update_document_source_type(
    document_id: str,
    req: SourceTypeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    previous_source_type = document.source_type
    previous_score = authority_score(previous_source_type)
    score = authority_score(req.source_type)
    qdrant_updated = False
    try:
        await qdrant_client.set_payload(
            collection_name=COLLECTION_NAME,
            payload={
                "source_type": req.source_type.value,
                "authority_score": score,
            },
            points=Filter(
                must=[
                    FieldCondition(
                        key="document_id", match=MatchValue(value=document_id)
                    )
                ]
            ),
            wait=True,
        )
        qdrant_updated = True
        document.source_type = req.source_type.value
        await db.commit()
    except Exception:
        await db.rollback()
        if qdrant_updated:
            await _restore_qdrant_payload(
                document_id,
                {
                    "source_type": previous_source_type,
                    "authority_score": previous_score,
                },
            )
        raise
    invalidate_bm25_index()
    await bump_semantic_cache_corpus_version()
    return {
        "document_id": document_id,
        "source_type": req.source_type.value,
        "authority_score": score,
    }
