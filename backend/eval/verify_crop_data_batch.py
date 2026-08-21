"""Verify an ingested crop-data batch across Postgres and Qdrant."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from qdrant_client.models import FieldCondition, Filter, MatchValue
from sqlalchemy import select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.db import AsyncSessionLocal
from app.core.qdrant_client import qdrant_client
from app.persistence.models import Document, DocumentChunk
from app.retrieval.qdrant_setup import COLLECTION_NAME
from eval.ingest_crop_data_batch import DEFAULT_MANIFEST, load_manifest


logger = logging.getLogger(__name__)


async def verify(manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, int]:
    manifest = load_manifest(manifest_path)
    entries = {entry["title"]: entry for entry in manifest["documents"]}
    async with AsyncSessionLocal() as db:
        documents = (
            await db.execute(select(Document).where(Document.title.in_(entries)))
        ).scalars().all()
        chunks = (
            await db.execute(
                select(DocumentChunk).where(
                    DocumentChunk.document_id.in_([document.id for document in documents])
                )
            )
        ).scalars().all()

    chunks_by_document: dict[str, list[DocumentChunk]] = {}
    for chunk in chunks:
        chunks_by_document.setdefault(str(chunk.document_id), []).append(chunk)

    active_count = 0
    inactive_count = 0
    qdrant_points = 0
    for title, entry in entries.items():
        matching = [document for document in documents if document.title == title]
        active = [document for document in matching if document.is_active]
        if len(active) != 1:
            raise ValueError(f"crop_batch_active_document_count:{title}:{len(active)}")
        current = active[0]
        expected_version = entry.get("version", manifest["version"])
        if (
            current.source != entry["source"]
            or current.source_type != entry["source_type"]
            or current.version != expected_version
        ):
            raise ValueError(f"crop_batch_active_document_metadata:{title}")
        active_count += 1
        inactive_count += sum(not document.is_active for document in matching)

        for document in matching:
            db_chunks = chunks_by_document.get(str(document.id), [])
            if not db_chunks:
                raise ValueError(f"crop_batch_document_chunks_missing:{document.id}")
            points, _ = await qdrant_client.scroll(
                collection_name=COLLECTION_NAME,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=str(document.id)),
                        )
                    ]
                ),
                limit=100,
                with_payload=True,
                with_vectors=False,
            )
            if len(points) != len(db_chunks):
                raise ValueError(f"crop_batch_qdrant_chunk_count:{document.id}")
            for point in points:
                payload = point.payload or {}
                if payload.get("is_active") is not document.is_active:
                    raise ValueError(f"crop_batch_qdrant_active_drift:{document.id}")
                if payload.get("title") != title or payload.get("source") != entry["source"]:
                    raise ValueError(f"crop_batch_qdrant_metadata_drift:{document.id}")
            qdrant_points += len(points)

    return {
        "manifest_documents": len(entries),
        "active_documents": active_count,
        "inactive_superseded_documents": inactive_count,
        "postgres_chunks": len(chunks),
        "qdrant_points": qdrant_points,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    logger.info("Crop data verification: %s", asyncio.run(verify(args.manifest)))


if __name__ == "__main__":
    main()
