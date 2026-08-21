import hashlib
import logging
import uuid
from datetime import datetime

from qdrant_client.models import (
    PointStruct,
    PointIdsList,
    Filter,
    FieldCondition,
    MatchValue,
)
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.qdrant_client import qdrant_client
from app.retrieval.qdrant_setup import COLLECTION_NAME
from app.retrieval.bm25_search import invalidate_bm25_index
from app.retrieval.chunking import chunk_text
from app.services.embedding_client import embed_batch
from app.services.semantic_cache import bump_semantic_cache_corpus_version
from app.persistence.models import Document, DocumentChunk
from app.retrieval.source_authority import (
    SourceType,
    authority_score,
    normalize_source_type,
)

logger = logging.getLogger(__name__)


def _document_title_lock_key(title: str) -> int:
    """Map an exact title to PostgreSQL's signed 64-bit advisory-lock key."""
    digest = hashlib.sha256(title.encode("utf-8")).digest()[:8]
    return int.from_bytes(digest, byteorder="big", signed=True)


async def _lock_document_title(db: AsyncSession, title: str) -> None:
    """Serialize active-version replacement, including a title's first insert."""
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": _document_title_lock_key(title)},
    )


async def _active_documents(db: AsyncSession, title: str) -> list[Document]:
    result = await db.execute(
        select(Document).where(Document.title == title, Document.is_active == True)
    )
    return list(result.scalars().all())


async def _set_document_active(document_id: str, active: bool) -> None:
    await qdrant_client.set_payload(
        collection_name=COLLECTION_NAME,
        payload={"is_active": active},
        points=Filter(
            must=[
                FieldCondition(
                    key="document_id",
                    match=MatchValue(value=document_id),
                )
            ]
        ),
        wait=True,
    )


async def _set_document_published_date(
    document_id: str, published_date: datetime | None
) -> None:
    await qdrant_client.set_payload(
        collection_name=COLLECTION_NAME,
        payload={
            "published_date": (
                published_date.isoformat() if published_date else None
            )
        },
        points=Filter(
            must=[
                FieldCondition(
                    key="document_id",
                    match=MatchValue(value=document_id),
                )
            ]
        ),
        wait=True,
    )


async def _compensate_failed_ingest(
    point_ids: list[str], old_documents: list[Document]
) -> None:
    if point_ids:
        try:
            await qdrant_client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=PointIdsList(points=point_ids),
            )
        except Exception:
            logger.error(
                "Failed to delete inactive Qdrant points after ingest error",
                exc_info=True,
            )
    for old_document in old_documents:
        try:
            await _set_document_active(str(old_document.id), True)
        except Exception:
            logger.error(
                "Failed to restore prior Qdrant document after ingest error",
                extra={"document_id": str(old_document.id)},
                exc_info=True,
            )


async def ingest_document(
    db: AsyncSession,
    title: str,
    content: str,
    source: str = None,
    source_type: str | SourceType = SourceType.UNKNOWN,
    author: str = None,
    version: str = None,
    file_key: str = None,
    published_date: datetime | None = None,
):
    normalized_source_type = normalize_source_type(source_type)
    chunks = chunk_text(content)
    if not chunks:
        raise ValueError("document produced no chunks")
    embeddings = await embed_batch(chunks)
    if len(embeddings) != len(chunks):
        raise RuntimeError("embedding service returned an incomplete batch")

    await _lock_document_title(db, title)
    old_docs = await _active_documents(db, title)
    document_id = uuid.uuid4()
    document = Document(
        id=document_id,
        title=title,
        source=source,
        source_type=normalized_source_type.value,
        author=author,
        version=version,
        published_date=published_date,
        is_active=False,
        file_key=file_key,
    )

    points = []
    point_ids: list[str] = []
    for i, (chunk_content, embedding) in enumerate(zip(chunks, embeddings)):
        point_id = str(uuid.uuid4())
        point_ids.append(point_id)
        points.append(
            PointStruct(
                id=point_id,
                vector=embedding,
                payload={
                    "document_id": str(document.id),
                    "chunk_id": point_id,
                    "chunk_index": i,
                    "content": chunk_content,
                    "title": title,
                    "source": source,
                    "source_type": normalized_source_type.value,
                    "authority_score": authority_score(normalized_source_type),
                    "version": version,
                    "published_date": (
                        published_date.isoformat() if published_date else None
                    ),
                    "is_active": False,
                    "locator": source,
                },
            )
        )
    try:
        db.add(document)
        for i, chunk_content in enumerate(chunks):
            db.add(
                DocumentChunk(
                    document_id=document.id,
                    qdrant_point_id=point_ids[i],
                    chunk_index=i,
                    content_preview=chunk_content[:200],
                )
            )
        await db.flush()
        await qdrant_client.upsert(
            collection_name=COLLECTION_NAME, points=points, wait=True
        )
        for old_document in old_docs:
            await _set_document_active(str(old_document.id), False)
            old_document.is_active = False
        await _set_document_active(str(document.id), True)
        document.is_active = True
        await db.commit()
    except Exception:
        await db.rollback()
        await _compensate_failed_ingest(point_ids, old_docs)
        raise
    invalidate_bm25_index()
    await bump_semantic_cache_corpus_version()

    return document


async def update_document_published_date(
    db: AsyncSession,
    document: Document,
    published_date: datetime | None,
) -> None:
    """Keep relational and vector evidence metadata in sync."""
    previous_published_date = document.published_date
    qdrant_updated = False
    try:
        await _set_document_published_date(str(document.id), published_date)
        qdrant_updated = True
        document.published_date = published_date
        await db.commit()
    except Exception:
        await db.rollback()
        if qdrant_updated:
            try:
                await _set_document_published_date(
                    str(document.id), previous_published_date
                )
            except Exception:
                logger.error(
                    "Failed to restore Qdrant published date after database error",
                    extra={"document_id": str(document.id)},
                    exc_info=True,
                )
        raise
    invalidate_bm25_index()
    await bump_semantic_cache_corpus_version()
