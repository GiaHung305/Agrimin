"""Backfill source authority metadata for existing Qdrant evidence points."""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from sqlalchemy import select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.db import AsyncSessionLocal
from app.core.qdrant_client import qdrant_client
from app.repository.models import Document
from app.retrieval.qdrant_setup import COLLECTION_NAME
from app.retrieval.source_authority import authority_score, normalize_source_type

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def metadata_for_payload(payload: dict, document_types: dict[str, str]) -> dict:
    source_type = normalize_source_type(
        document_types.get(str(payload.get("document_id")))
        or payload.get("source_type")
    )
    return {
        "source_type": source_type.value,
        "authority_score": authority_score(source_type),
    }


async def migrate() -> None:
    async with AsyncSessionLocal() as db:
        rows = await db.execute(select(Document.id, Document.source_type))
        document_types = {str(row.id): row.source_type for row in rows.all()}

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
                payload=metadata_for_payload(point.payload or {}, document_types),
                points=[point.id],
            )
            updated += 1
        if offset is None:
            break
    logger.info("Backfilled source authority for %s Qdrant points", updated)


if __name__ == "__main__":
    asyncio.run(migrate())
