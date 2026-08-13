"""Apply an audited soft-deactivation manifest to Postgres and Qdrant."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from qdrant_client.models import FieldCondition, Filter, MatchValue
from sqlalchemy import select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.db import AsyncSessionLocal
from app.core.qdrant_client import qdrant_client
from app.repository.models import Document
from app.retrieval.bm25_search import invalidate_bm25_index
from app.retrieval.qdrant_setup import COLLECTION_NAME
from app.services.semantic_cache import bump_semantic_cache_corpus_version

logger = logging.getLogger(__name__)
DEFAULT_MANIFEST = Path(__file__).with_name("corpus_cleanup_crop_scope_v1.json")


def load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("action") != "soft_deactivate":
        raise ValueError("cleanup_manifest_action_must_be_soft_deactivate")
    documents = payload.get("documents")
    if not isinstance(documents, list) or not documents:
        raise ValueError("cleanup_manifest_documents_required")
    ids = [str(item.get("id", "")) for item in documents]
    if len(ids) != len(set(ids)):
        raise ValueError("cleanup_manifest_duplicate_document_id")
    for item in documents:
        uuid.UUID(str(item.get("id")))
        for field in ("title", "source", "category", "reason"):
            if not str(item.get(field, "")).strip():
                raise ValueError(f"cleanup_manifest_{field}_required")
    return payload


def validate_document(entry: dict[str, Any], document: Document) -> None:
    if document.title != entry["title"]:
        raise ValueError(f"cleanup_title_mismatch:{document.id}")
    if document.source != entry["source"]:
        raise ValueError(f"cleanup_source_mismatch:{document.id}")


async def apply_cleanup(
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    apply: bool = False,
) -> dict[str, int]:
    manifest = load_manifest(manifest_path)
    entries = manifest["documents"]
    ids = [uuid.UUID(entry["id"]) for entry in entries]

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Document).where(Document.id.in_(ids)))
        documents = {str(document.id): document for document in result.scalars().all()}
        missing = sorted(set(map(str, ids)) - set(documents))
        if missing:
            raise ValueError(f"cleanup_documents_missing:{','.join(missing)}")
        for entry in entries:
            validate_document(entry, documents[entry["id"]])

        active_before = sum(
            bool(documents[entry["id"]].is_active) for entry in entries
        )
        summary = {
            "matched": len(entries),
            "active_before": active_before,
            "already_inactive": len(entries) - active_before,
            "deactivated": 0,
        }
        if not apply:
            return summary

        for entry in entries:
            documents[entry["id"]].is_active = False
        await db.commit()

    for entry in entries:
        await qdrant_client.set_payload(
            collection_name=COLLECTION_NAME,
            payload={"is_active": False},
            points=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=entry["id"]),
                    )
                ]
            ),
        )

    invalidate_bm25_index()
    if active_before:
        await bump_semantic_cache_corpus_version()
    summary["deactivated"] = active_before
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist soft-deactivation. Without this flag the command is read-only.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    summary = asyncio.run(apply_cleanup(args.manifest, apply=args.apply))
    logger.info("Corpus cleanup summary: %s", summary)


if __name__ == "__main__":
    main()
