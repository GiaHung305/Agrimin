"""Canonical evidence records shared by retrieval, generation, and the API."""

from __future__ import annotations

import hashlib
from typing import Any

from app.core.config import settings
from app.retrieval.source_authority import authority_score, normalize_source_type


def evidence_identity(record: dict[str, Any]) -> str:
    """Return a stable chunk identity, including a safe legacy fallback."""
    document_id = record.get("document_id")
    chunk_id = record.get("chunk_id") or record.get("qdrant_point_id")
    if document_id and chunk_id:
        return f"{document_id}:{chunk_id}"
    content = str(record.get("content") or "")
    return "legacy:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def normalize_evidence(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize Qdrant/search payloads without discarding ranking signals."""
    source = record.get("source")
    locator = record.get("locator") or record.get("source_url") or source
    chunk_id = record.get("chunk_id") or record.get("qdrant_point_id")
    normalized = {
        "document_id": record.get("document_id"),
        "chunk_id": str(chunk_id) if chunk_id is not None else None,
        "chunk_index": record.get("chunk_index"),
        "title": record.get("title"),
        "source": source,
        "source_type": normalize_source_type(record.get("source_type")).value,
        "authority_score": authority_score(record.get("source_type")),
        "version": record.get("version"),
        "locator": locator,
        "is_active": record.get("is_active", True),
        "content": str(record.get("content") or ""),
        "ranking_strategy": record.get("ranking_strategy"),
        "research_questions": [
            str(question)
            for question in record.get("research_questions", [])
            if str(question).strip()
        ],
    }
    for score_name in ("dense_score", "bm25_score", "fusion_score", "rerank_score"):
        score = record.get(score_name)
        normalized[score_name] = float(score) if score is not None else None
    return normalized


def citation_from_evidence(record: dict[str, Any]) -> dict[str, Any]:
    evidence = normalize_evidence(record)
    return {
        "title": evidence["title"] or evidence["source"] or "Tai lieu noi bo",
        "url": evidence["locator"],
        "type": "internal",
        "document_id": evidence["document_id"],
        "chunk_id": evidence["chunk_id"],
        "chunk_index": evidence["chunk_index"],
        "source": evidence["source"],
        "source_type": evidence["source_type"],
        "authority_score": evidence["authority_score"],
        "version": evidence["version"],
        "is_active": evidence["is_active"],
        "retrieval_score": evidence["fusion_score"],
        "rerank_score": evidence["rerank_score"],
    }


def is_traceable_active_evidence(record: dict[str, Any]) -> bool:
    evidence = normalize_evidence(record)
    return bool(
        evidence["document_id"]
        and evidence["chunk_id"]
        and evidence["is_active"] is True
        and evidence["content"]
    )


def is_excluded_source(record: dict[str, Any]) -> bool:
    excluded = {
        item.strip().casefold()
        for item in settings.retrieval_excluded_sources.split(",")
        if item.strip()
    }
    return str(record.get("source") or "").strip().casefold() in excluded
