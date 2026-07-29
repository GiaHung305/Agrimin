import uuid
from datetime import datetime

from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.qdrant_client import qdrant_client
from app.retrieval.qdrant_setup import COLLECTION_NAME
from app.retrieval.chunking import chunk_text
from app.services.embedding_client import embed_batch
from app.repository.models import Document, DocumentChunk


async def deactivate_old_versions(db: AsyncSession, title: str):
    result = await db.execute(
        select(Document).where(Document.title == title, Document.is_active == True)
    )
    old_docs = result.scalars().all()

    for doc in old_docs:
        doc.is_active = False
        await qdrant_client.set_payload(
            collection_name=COLLECTION_NAME,
            payload={"is_active": False},
            points=Filter(
                must=[FieldCondition(key="document_id", match=MatchValue(value=str(doc.id)))]
            ),
        )

    await db.commit()


async def ingest_document(
    db: AsyncSession,
    title: str,
    content: str,
    source: str = None,
    author: str = None,
    version: str = None,
    file_key: str = None,
):
    await deactivate_old_versions(db, title)

    document = Document(
        title=title,
        source=source,
        author=author,
        version=version,
        published_date=datetime.utcnow(),
        is_active=True,
        file_key=file_key,
    )
    db.add(document)
    await db.flush()

    chunks = chunk_text(content)
    embeddings = await embed_batch(chunks)

    points = []
    for i, (chunk_content, embedding) in enumerate(zip(chunks, embeddings)):
        point_id = str(uuid.uuid4())
        points.append(
            PointStruct(
                id=point_id,
                vector=embedding,
                payload={
                    "document_id": str(document.id),
                    "chunk_index": i,
                    "content": chunk_content,
                    "title": title,
                    "source": source,
                    "version": version,
                    "is_active": True,
                },
            )
        )
        db.add(
            DocumentChunk(
                document_id=document.id,
                qdrant_point_id=point_id,
                chunk_index=i,
                content_preview=chunk_content[:200],
            )
        )

    await qdrant_client.upsert(collection_name=COLLECTION_NAME, points=points)
    await db.commit()

    return document