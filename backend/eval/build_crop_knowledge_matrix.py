"""Build an audited crop knowledge coverage matrix from active corpus sources."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.db import AsyncSessionLocal
from app.persistence.models import Document
from app.services.farm_monitoring import POLICIES, SUPPORTED_VEGETABLE_POLICY_KEYS


DEFAULT_REGISTRY = Path(__file__).with_name("crop_knowledge_source_tags_v1.json")
DEFAULT_OUTPUT = Path(__file__).with_name("crop_knowledge_coverage_report_v1.json")
ALLOWED_GROUPS = {"all_crops", "vegetables"}
BASELINE_STAGE = "all"
BASELINE_REGION = "national"
logger = logging.getLogger(__name__)


def load_registry(path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    dimensions = payload.get("dimensions", {})
    topics = set(dimensions.get("topics", []))
    stages = set(dimensions.get("stages", []))
    regions = set(dimensions.get("regions", []))
    if not topics or not stages or not regions:
        raise ValueError("source_registry_dimensions_required")

    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("source_registry_sources_required")
    source_names = [str(item.get("source", "")).strip() for item in sources]
    if any(not source for source in source_names):
        raise ValueError("source_registry_source_required")
    if len(source_names) != len(set(source_names)):
        raise ValueError("source_registry_duplicate_source")

    policy_keys = set(POLICIES)
    for rule in sources:
        if not str(rule.get("source_type", "")).strip():
            raise ValueError("source_registry_source_type_required")
        crop_keys = set(rule.get("crop_keys", []))
        crop_groups = set(rule.get("crop_groups", []))
        rule_topics = set(rule.get("topics", []))
        rule_stages = set(rule.get("stages", []))
        rule_regions = set(rule.get("regions", []))
        if crop_keys - policy_keys:
            raise ValueError(
                "source_registry_unknown_crop_keys:"
                + ",".join(sorted(crop_keys - policy_keys))
            )
        if crop_groups - ALLOWED_GROUPS:
            raise ValueError(
                "source_registry_unknown_crop_groups:"
                + ",".join(sorted(crop_groups - ALLOWED_GROUPS))
            )
        if rule_topics - topics:
            raise ValueError("source_registry_unknown_topics")
        if rule_stages - (stages | {BASELINE_STAGE}):
            raise ValueError("source_registry_unknown_stages")
        if rule_regions - (regions | {BASELINE_REGION}):
            raise ValueError("source_registry_unknown_regions")
        if rule.get("count_for_coverage", True) and not (
            crop_keys or crop_groups
        ):
            raise ValueError("source_registry_coverage_scope_required")
    return payload


def _rule_applies(rule: dict[str, Any], crop_key: str) -> bool:
    if crop_key in set(rule.get("crop_keys", [])):
        return True
    groups = set(rule.get("crop_groups", []))
    return "all_crops" in groups or (
        "vegetables" in groups and crop_key in SUPPORTED_VEGETABLE_POLICY_KEYS
    )


def _source_inventory(
    active_sources: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    inventory: dict[str, dict[str, Any]] = {}
    duplicate_type_sources: list[str] = []
    for item in active_sources:
        source = str(item["source"])
        source_type = str(item["source_type"])
        existing = inventory.get(source)
        if existing and existing["source_type"] != source_type:
            duplicate_type_sources.append(source)
            continue
        if existing:
            existing["documents"] += int(item.get("documents", 0))
        else:
            inventory[source] = {
                "source_type": source_type,
                "documents": int(item.get("documents", 0)),
            }
    return inventory, sorted(set(duplicate_type_sources))


def build_report(
    registry: dict[str, Any], active_sources: list[dict[str, Any]]
) -> dict[str, Any]:
    dimensions = registry["dimensions"]
    topics = list(dimensions["topics"])
    stages = list(dimensions["stages"])
    regions = list(dimensions["regions"])
    registry_rules = {item["source"]: item for item in registry["sources"]}
    inventory, duplicate_type_sources = _source_inventory(active_sources)

    active_names = set(inventory)
    registered_names = set(registry_rules)
    unclassified = sorted(active_names - registered_names)
    missing = sorted(registered_names - active_names)
    type_mismatches = sorted(
        source
        for source in active_names & registered_names
        if inventory[source]["source_type"]
        != registry_rules[source]["source_type"]
    )
    blockers = []
    if unclassified:
        blockers.append({"code": "unclassified_active_sources", "sources": unclassified})
    if missing:
        blockers.append({"code": "registered_sources_not_active", "sources": missing})
    if type_mismatches:
        blockers.append({"code": "source_type_mismatches", "sources": type_mismatches})
    if duplicate_type_sources:
        blockers.append(
            {"code": "active_source_has_multiple_types", "sources": duplicate_type_sources}
        )

    active_rules = [
        registry_rules[source]
        for source in sorted(active_names & registered_names)
        if source not in type_mismatches
        and registry_rules[source].get("count_for_coverage", True)
    ]

    crops: list[dict[str, Any]] = []
    backlog: list[dict[str, Any]] = []
    total_cell_counts: Counter[str] = Counter()
    priority_counts: Counter[str] = Counter()
    for crop_key, policy in sorted(POLICIES.items()):
        applicable = [rule for rule in active_rules if _rule_applies(rule, crop_key)]
        specific = [rule for rule in applicable if crop_key in rule.get("crop_keys", [])]
        covered_topics = sorted(
            {topic for rule in applicable for topic in rule.get("topics", [])}
        )
        topic_gaps = [topic for topic in topics if topic not in covered_topics]
        stage_specific_covered = sorted(
            {
                stage
                for rule in applicable
                for stage in rule.get("stages", [])
                if stage in stages
            }
        )
        region_specific_covered = sorted(
            {
                region
                for rule in applicable
                for region in rule.get("regions", [])
                if region in regions
            }
        )

        cell_counts: Counter[str] = Counter()
        for topic in topics:
            for stage in stages:
                for region in regions:
                    matches = [
                        rule
                        for rule in applicable
                        if topic in rule.get("topics", [])
                        and (
                            stage in rule.get("stages", [])
                            or BASELINE_STAGE in rule.get("stages", [])
                        )
                        and (
                            region in rule.get("regions", [])
                            or BASELINE_REGION in rule.get("regions", [])
                        )
                    ]
                    if any(
                        stage in rule.get("stages", [])
                        and region in rule.get("regions", [])
                        for rule in matches
                    ):
                        cell_counts["covered"] += 1
                    elif matches:
                        cell_counts["baseline_only"] += 1
                    else:
                        cell_counts["gap"] += 1
        cell_counts["total"] = len(topics) * len(stages) * len(regions)

        if not specific:
            priority = "P0"
        elif len(specific) < 2 or len(topic_gaps) >= 3:
            priority = "P1"
        else:
            priority = "P2"
        priority_counts[priority] += 1
        total_cell_counts.update(cell_counts)

        crop = {
            "key": crop_key,
            "label": policy.crop_label,
            "mode": policy.mode,
            "is_vegetable": crop_key in SUPPORTED_VEGETABLE_POLICY_KEYS,
            "evidence_sources": len(applicable),
            "crop_specific_sources": len(specific),
            "topics_covered": covered_topics,
            "topic_gaps": topic_gaps,
            "stage_specific_covered": stage_specific_covered,
            "stage_specific_gaps": [
                stage for stage in stages if stage not in stage_specific_covered
            ],
            "region_specific_covered": region_specific_covered,
            "region_specific_gaps": [
                region for region in regions if region not in region_specific_covered
            ],
            "cells": dict(cell_counts),
            "priority": priority,
        }
        crops.append(crop)
        backlog.append(
            {
                "priority": priority,
                "crop_key": crop_key,
                "crop_label": policy.crop_label,
                "crop_specific_sources": len(specific),
                "topic_gaps": topic_gaps,
                "stage_gaps": crop["stage_specific_gaps"],
                "region_gaps": crop["region_specific_gaps"],
                "recommended_source_classes": [
                    "Vietnamese government/extension crop protocol",
                    "international agricultural organization guidance",
                    "peer-reviewed source only for unresolved specialist gaps",
                ],
            }
        )

    order = {"P0": 0, "P1": 1, "P2": 2}
    backlog.sort(key=lambda item: (order[item["priority"]], item["crop_key"]))
    return {
        "version": "crop-knowledge-coverage-v1",
        "source_tag_version": registry["version"],
        "dimensions": dimensions,
        "inventory": {
            "active_sources": len(active_names),
            "classified_active_sources": len(active_names & registered_names),
            "unclassified_active_sources": unclassified,
            "registered_sources_not_active": missing,
            "source_type_mismatches": type_mismatches,
        },
        "summary": {
            "crops": len(crops),
            "cells": dict(total_cell_counts),
            "priorities": dict(priority_counts),
        },
        "blockers": blockers,
        "crops": crops,
        "backlog": backlog,
    }


async def load_active_sources() -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Document.source, Document.source_type, func.count(Document.id))
            .where(Document.is_active.is_(True))
            .group_by(Document.source, Document.source_type)
            .order_by(Document.source, Document.source_type)
        )
    return [
        {"source": source, "source_type": source_type, "documents": count}
        for source, source_type, count in result.all()
    ]


async def run(registry_path: Path, output_path: Path, *, strict: bool) -> dict[str, Any]:
    registry = load_registry(registry_path)
    report = build_report(registry, await load_active_sources())
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if strict and report["blockers"]:
        raise RuntimeError(
            "knowledge_matrix_blockers:" + ",".join(
                blocker["code"] for blocker in report["blockers"]
            )
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    report = asyncio.run(run(args.registry, args.output, strict=args.strict))
    logger.info(
        "Knowledge matrix summary: %s",
        {"inventory": report["inventory"], "summary": report["summary"]},
    )


if __name__ == "__main__":
    main()
