"""Smoke-evaluate Gemini Vision through the canonical authenticated SSE API."""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import sys
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.core.model_registry import ModelRole, model_name, runtime_fingerprint
from eval.run_eval import get_supabase_token, invoke_production_chat


def plantdoc_test_cases(
    names: list[str],
    label_map: dict[str, str],
    limit: int,
    scope_offset: int = 0,
) -> list[tuple[str, str]]:
    """Choose a deterministic, balanced tomato/non-tomato smoke set."""
    if limit < 2:
        raise ValueError("limit must be at least 2")
    if scope_offset < 0:
        raise ValueError("scope_offset must not be negative")
    tomato: list[tuple[str, str]] = []
    non_tomato_by_class: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for member in names:
        parts = member.split("/")
        if len(parts) != 4 or parts[1] != "test" or member.endswith("/"):
            continue
        source_class = parts[2]
        if source_class in label_map:
            tomato.append((member, "tomato"))
        elif not source_class.casefold().startswith("tomato"):
            non_tomato_by_class[source_class].append((member, "non_tomato"))

    half = limit // 2
    ordered_tomato = sorted(
        tomato, key=lambda item: hashlib.sha256(item[0].encode()).hexdigest()
    )[scope_offset:scope_offset + half]
    non_tomato: list[tuple[str, str]] = []
    for source_class in sorted(non_tomato_by_class):
        ordered = sorted(
            non_tomato_by_class[source_class],
            key=lambda item: hashlib.sha256(item[0].encode()).hexdigest(),
        )
        if ordered:
            non_tomato.append(ordered[0])
    ordered_non_tomato = sorted(
        non_tomato, key=lambda item: hashlib.sha256(item[0].encode()).hexdigest()
    )[scope_offset:scope_offset + limit - len(ordered_tomato)]
    return ordered_tomato + ordered_non_tomato


def _mime_type(member: str) -> str:
    suffix = Path(member).suffix.casefold()
    return {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}.get(
        suffix, "image/jpeg"
    )


def _is_tomato(candidate: Any) -> bool:
    value = " ".join(str(candidate or "").casefold().split())
    return "tomato" in value or "cà chua" in value


def _is_successful_analysis(vision: dict[str, Any], observation: dict[str, Any]) -> bool:
    """Only score crop scope when a typed provider observation was produced."""
    return (
        vision.get("mode") == "typed_observations"
        and not vision.get("error")
        and bool(observation)
    )


async def run(args: argparse.Namespace) -> dict[str, Any]:
    if not args.allow_provider_calls:
        raise RuntimeError("pass --allow-provider-calls to acknowledge Gemini API usage")
    if not settings.vision_analysis_enabled:
        raise RuntimeError("benchmark API must run with VISION_ANALYSIS_ENABLED=true")

    label_map = json.loads(args.label_map.read_text(encoding="utf-8"))
    with zipfile.ZipFile(args.archive) as archive:
        cases = plantdoc_test_cases(
            archive.namelist(),
            label_map,
            args.limit,
            scope_offset=args.scope_offset,
        )
        payloads = [
            (member, expected, archive.read(member)) for member, expected in cases
        ]

    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=args.timeout) as client:
        token = await get_supabase_token(client)
        for index, (member, expected, raw_bytes) in enumerate(payloads):
            try:
                response = await invoke_production_chat(
                    client,
                    token,
                    "Hãy mô tả khách quan cây và các đặc điểm nhìn thấy trong ảnh. Không chẩn đoán bệnh.",
                    images=[{
                        "mime_type": _mime_type(member),
                        "data_base64": base64.b64encode(raw_bytes).decode("ascii"),
                    }],
                )
                vision = (response.get("trace") or {}).get("vision") or {}
                observations = vision.get("visual_observations") or []
                observation = observations[0] if observations else {}
                candidate_is_tomato = _is_tomato(observation.get("crop_candidate"))
                correct_crop_scope = _is_successful_analysis(vision, observation) and (
                    candidate_is_tomato
                    if expected == "tomato"
                    else not candidate_is_tomato
                )
                results.append({
                    "case_id": hashlib.sha256(member.encode()).hexdigest()[:12],
                    "expected_scope": expected,
                    "vision_error": vision.get("error"),
                    "vision_mode": vision.get("mode"),
                    "chat_provider_status": ((response.get("trace") or {}).get("provider") or {}).get("status"),
                    "relevance": observation.get("relevance"),
                    "crop_candidate": observation.get("crop_candidate"),
                    "confidence": observation.get("confidence"),
                    "symptom_count": len(observation.get("visible_symptoms") or []),
                    "correct_crop_scope": correct_crop_scope,
                })
            except (httpx.HTTPError, ValueError) as exc:
                results.append({
                    "case_id": hashlib.sha256(member.encode()).hexdigest()[:12],
                    "expected_scope": expected,
                    "request_error": type(exc).__name__,
                    "correct_crop_scope": False,
                })
            if index + 1 < len(payloads):
                await asyncio.sleep(args.delay)

    successful = [
        item for item in results
        if item.get("vision_mode") == "typed_observations"
        and not item.get("vision_error")
        and not item.get("request_error")
    ]
    tomato_results = [item for item in results if item["expected_scope"] == "tomato"]
    non_tomato_results = [item for item in results if item["expected_scope"] == "non_tomato"]
    report = {
        "dataset": "plantdoc-test-smoke-v1",
        "runtime_fingerprint": runtime_fingerprint(),
        "vision_model": model_name(ModelRole.VISION),
        "sample_size": len(results),
        "successful_analysis_rate": len(successful) / max(len(results), 1),
        "tomato_recall": sum(item["correct_crop_scope"] for item in tomato_results) / max(len(tomato_results), 1),
        "non_tomato_separation": sum(item["correct_crop_scope"] for item in non_tomato_results) / max(len(non_tomato_results), 1),
        "cases": results,
        "promotion_pass": False,
        "promotion_blockers": [
            "smoke_sample_is_not_a_versioned_full_field_and_ood_benchmark",
            "production_feature_flag_rollout_not_completed",
        ],
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--label-map", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--scope-offset", type=int, default=0)
    parser.add_argument("--delay", type=float, default=7.0)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--allow-provider-calls", action="store_true")
    args = parser.parse_args()
    report = asyncio.run(run(args))
    print(json.dumps({key: value for key, value in report.items() if key != "cases"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
