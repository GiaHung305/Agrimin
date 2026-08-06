import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from qdrant_client.models import FieldCondition, Filter, MatchValue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_admin
from app.core.config import settings
from app.core.db import get_db
from app.core.qdrant_client import qdrant_client
from app.repository.models import Document
from app.retrieval.qdrant_setup import COLLECTION_NAME
from app.retrieval.bm25_search import invalidate_bm25_index
from app.services.ingest_service import ingest_document
from app.services.pdf_extractor import extract_text_from_pdf
from app.services.storage_service import upload_file

router = APIRouter(tags=["documents"])


class IngestRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=1_000_000)
    source: str | None = Field(default=None, max_length=255)
    author: str | None = Field(default=None, max_length=255)
    version: str | None = Field(default=None, max_length=50)


@router.post("/documents/ingest")
async def ingest(
    req: IngestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    file_key = f"documents/{uuid.uuid4()}_{req.title}.txt"
    await upload_file(req.content.encode("utf-8"), file_key, content_type="text/plain")

    document = await ingest_document(
        db=db,
        title=req.title,
        content=req.content,
        source=req.source,
        author=req.author,
        version=req.version,
        file_key=file_key,
    )
    return {"document_id": str(document.id), "title": document.title, "file_key": file_key}


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(..., min_length=1, max_length=500),
    source: str | None = Form(None, max_length=255),
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

    file_key = f"documents/{uuid.uuid4()}_{file.filename}"
    await upload_file(file_bytes, file_key, content_type="application/pdf")

    document = await ingest_document(
        db=db,
        title=title,
        content=content,
        source=source,
        author=author,
        version=version,
        file_key=file_key,
    )
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
            "version": document.version,
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

    document.is_active = False
    await db.commit()
    await qdrant_client.set_payload(
        collection_name=COLLECTION_NAME,
        payload={"is_active": False},
        points=Filter(
            must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
        ),
    )
    invalidate_bm25_index()
    return {"status": "deactivated", "document_id": document_id}
