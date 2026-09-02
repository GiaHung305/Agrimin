"""Backfill reviewed crop, stage, and region scope for Qdrant evidence."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.qdrant_client import qdrant_client
from app.retrieval.qdrant_setup import COLLECTION_NAME
from app.services.semantic_cache import bump_semantic_cache_corpus_version


DEFAULT_REGISTRY = Path(__file__).with_name("crop_knowledge_source_tags_v1.json")
logger = logging.getLogger(__name__)


SCOPE_FIELDS = ("crop_keys", "stages", "regions")


def load_source_scopes(
    path: Path = DEFAULT_REGISTRY,
) -> dict[str, dict[str, list[str]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    mapping: dict[str, dict[str, set[str]]] = {}
    for entry in payload.get("sources", []):
        source = str(entry.get("source") or "").strip()
        if not source:
            continue
        scope = mapping.setdefault(
            source, {field: set() for field in SCOPE_FIELDS}
        )
        for field in SCOPE_FIELDS:
            scope[field].update(
                str(value).strip()
                for value in (entry.get(field) or [])
                if str(value).strip()
            )
    return {
        source: {field: sorted(values) for field, values in scope.items()}
        for source, scope in mapping.items()
    }


def load_source_crop_keys(path: Path = DEFAULT_REGISTRY) -> dict[str, list[str]]:
    """Compatibility view used by older tooling and focused tests."""
    return {
        source: scope["crop_keys"]
        for source, scope in load_source_scopes(path).items()
    }


def crop_scope_for_payload(
    payload: dict[str, Any], source_crop_keys: dict[str, list[str]]
) -> list[str]:
    existing = {
        str(crop_key).strip()
        for crop_key in (payload.get("crop_keys") or [])
        if str(crop_key).strip()
    }
    if existing:
        return sorted(existing)
    return list(source_crop_keys.get(str(payload.get("source") or ""), []))


def evidence_scope_for_payload(
    payload: dict[str, Any],
    source_scopes: dict[str, dict[str, list[str]]],
) -> dict[str, list[str]]:
    reviewed = source_scopes.get(str(payload.get("source") or ""), {})
    return {
        field: sorted({
            str(value).strip()
            for value in (payload.get(field) or reviewed.get(field) or [])
            if str(value).strip()
        })
        for field in SCOPE_FIELDS
    }


async def migrate(*, apply: bool, registry_path: Path = DEFAULT_REGISTRY) -> dict:
    source_scopes = load_source_scopes(registry_path)
    offset = None
    scanned = 0
    matched = 0
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
            scanned += 1
            payload = point.payload or {}
            scope = evidence_scope_for_payload(payload, source_scopes)
            if not any(scope.values()):
                continue
            matched += 1
            changed = {
                field: values
                for field, values in scope.items()
                if sorted({
                    str(value).strip()
                    for value in (payload.get(field) or [])
                    if str(value).strip()
                }) != values
            }
            if not changed:
                continue
            if apply:
                await qdrant_client.set_payload(
                    collection_name=COLLECTION_NAME,
                    payload=changed,
                    points=[point.id],
                    wait=True,
                )
            updated += 1
        if offset is None:
            break
    if apply and updated:
        await bump_semantic_cache_corpus_version()
    return {
        "mode": "apply" if apply else "dry_run",
        "scanned_points": scanned,
        "matched_points": matched,
        "updated_points": updated,
        "registry_sources": len(source_scopes),
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    result = await migrate(apply=args.apply, registry_path=args.registry)
    logger.info("Crop scope migration: %s", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
