"""Backfill authority and publication metadata for existing Qdrant evidence."""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from sqlalchemy import select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.db import AsyncSessionLocal
from app.core.qdrant_client import qdrant_client
from app.persistence.models import Document
from app.retrieval.qdrant_setup import COLLECTION_NAME
from app.retrieval.source_authority import authority_score, normalize_source_type
from app.services.semantic_cache import bump_semantic_cache_corpus_version

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def metadata_for_payload(payload: dict, document_metadata: dict[str, dict]) -> dict:
    relational = document_metadata.get(str(payload.get("document_id"))) or {}
    source_type = normalize_source_type(
        relational.get("source_type") or payload.get("source_type")
    )
    published_date = relational.get("published_date")
    return {
        "source_type": source_type.value,
        "authority_score": authority_score(source_type),
        "published_date": (
            published_date.isoformat()
            if hasattr(published_date, "isoformat")
            else published_date
        ),
    }


async def migrate() -> None:
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(Document.id, Document.source_type, Document.published_date)
        )
        document_metadata = {
            str(row.id): {
                "source_type": row.source_type,
                "published_date": row.published_date,
            }
            for row in rows.all()
        }

    offset = None
    updated = 0
    while True:
        points, offset = await qdrant_client.scroll(
            collection_name=COLLECTION_NAME,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in points:
            await qdrant_client.set_payload(
                collection_name=COLLECTION_NAME,
                payload=metadata_for_payload(
                    point.payload or {}, document_metadata
                ),
                points=[point.id],
            )
            updated += 1
        if offset is None:
            break
    await bump_semantic_cache_corpus_version()
    logger.info("Backfilled document metadata for %s Qdrant points", updated)


if __name__ == "__main__":
    asyncio.run(migrate())
