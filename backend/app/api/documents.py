import uuid

from fastapi import APIRouter, Depends, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from qdrant_client.models import Filter, FieldCondition, MatchValue

from app.core.db import get_db
from app.core.qdrant_client import qdrant_client
from app.retrieval.qdrant_setup import COLLECTION_NAME
from app.services.ingest_service import ingest_document
from app.services.pdf_extractor import extract_text_from_pdf
from app.services.storage_service import upload_file
from app.repository.models import Document
from app.core.auth import get_current_user

router = APIRouter(tags=["documents"])


class IngestRequest(BaseModel):
    title: str
    content: str
    source: str = None
    author: str = None
    version: str = None


@router.post("/documents/ingest")
async def ingest(
    req: IngestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
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
    title: str = Form(...),
    source: str = Form(None),
    author: str = Form(None),
    version: str = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if not file.filename.lower().endswith(".pdf"):
        return {"error": "Chỉ hỗ trợ file .pdf ở phiên bản này"}

    file_bytes = await file.read()
    content = extract_text_from_pdf(file_bytes)

    if not content.strip():
        return {"error": "Không trích xuất được text từ PDF (có thể là PDF scan ảnh, chưa hỗ trợ OCR)"}

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
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(select(Document).order_by(Document.ingested_at.desc()))
    docs = result.scalars().all()
    return [
        {
            "id": str(d.id),
            "title": d.title,
            "source": d.source,
            "version": d.version,
            "is_active": d.is_active,
            "ingested_at": d.ingested_at.isoformat(),
            "file_key": d.file_key,
        }
        for d in docs
    ]


@router.patch("/documents/{document_id}/deactivate")
async def deactivate_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        return {"error": "Không tìm thấy document"}

    doc.is_active = False
    await db.commit()

    await qdrant_client.set_payload(
        collection_name=COLLECTION_NAME,
        payload={"is_active": False},
        points=Filter(
            must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
        ),
    )

    return {"status": "deactivated", "document_id": document_id}