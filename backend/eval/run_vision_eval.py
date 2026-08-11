"""Evaluate vision safety through AgriMind's canonical authenticated SSE API."""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import sys
import zipfile
from collections import defaultdict
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

import httpx
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.core.model_registry import ModelRole, model_name, runtime_fingerprint
from app.multimodal.image_validation import validate_chat_image_payload
from eval.run_eval import get_supabase_token, invoke_production_chat


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = Path(__file__).with_name("vision_benchmark_v2.json")
DEFAULT_ARCHIVE = (
    REPOSITORY_ROOT
    / "vision_training/data/raw/archives/plantdoc_field_eval.zip"
)
DEFAULT_OOD_DIR = REPOSITORY_ROOT / "vision_training/data/raw/ood_eval_v1"
IMAGE_QUESTION = (
    "Hãy mô tả khách quan cây và các đặc điểm nhìn thấy trong ảnh. "
    "Không chẩn đoán bệnh."
)


def plantdoc_test_cases(
    names: list[str],
    label_map: dict[str, str],
    limit: int,
    scope_offset: int = 0,
) -> list[tuple[str, str]]:
    """Choose a deterministic, balanced tomato/non-tomato legacy smoke set."""
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


def _stable_members(
    names: list[str],
    *,
    split: str,
    source_class: str,
    count: int,
    member_is_eligible: Callable[[str], bool] | None = None,
) -> list[str]:
    matching = [
        member
        for member in names
        if not member.endswith("/")
        and len(member.split("/")) == 4
        and member.split("/")[1] == split
        and member.split("/")[2] == source_class
        and (member_is_eligible is None or member_is_eligible(member))
    ]
    ordered = sorted(
        matching, key=lambda member: hashlib.sha256(member.encode()).hexdigest()
    )
    if len(ordered) < count:
        raise ValueError(
            f"PlantDoc class {source_class!r} has {len(ordered)} images; {count} required"
        )
    return ordered[:count]


def plantdoc_benchmark_cases(
    names: list[str],
    manifest: dict[str, Any],
    member_is_eligible: Callable[[str], bool] | None = None,
) -> list[dict[str, Any]]:
    """Select a deterministic held-out healthy and look-alike PlantDoc set."""
    config = manifest["plantdoc"]
    split = config["split"]
    cases: list[dict[str, Any]] = []
    for source_class in config["healthy"]["classes"]:
        for member in _stable_members(
            names,
            split=split,
            source_class=source_class,
            count=int(config["healthy"]["samples_per_class"]),
            member_is_eligible=member_is_eligible,
        ):
            cases.append({
                "case_id": f"healthy-{hashlib.sha256(member.encode()).hexdigest()[:12]}",
                "category": "healthy",
                "source_class": source_class,
                "member": member,
            })

    for group in config["look_alike"]["groups"]:
        for source_class in group["classes"]:
            for member in _stable_members(
                names,
                split=split,
                source_class=source_class,
                count=int(group["samples_per_class"]),
                member_is_eligible=member_is_eligible,
            ):
                cases.append({
                    "case_id": f"lookalike-{hashlib.sha256(member.encode()).hexdigest()[:12]}",
                    "category": "look_alike",
                    "challenge_group": group["id"],
                    "source_class": source_class,
                    "member": member,
                })
    return cases


def _mime_type(filename: str) -> str:
    suffix = Path(filename).suffix.casefold()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(suffix, "image/jpeg")


def make_quality_variant(raw_bytes: bytes, variant: dict[str, Any]) -> bytes:
    """Create an in-memory JPEG variant without altering the held-out source file."""
    with Image.open(BytesIO(raw_bytes)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
    if variant["id"] == "dark":
        image = ImageEnhance.Brightness(image).enhance(
            float(variant["brightness_factor"])
        )
    elif variant["id"] == "blur":
        image = image.filter(
            ImageFilter.GaussianBlur(radius=float(variant["gaussian_radius"]))
        )
    else:
        raise ValueError(f"unsupported quality variant: {variant['id']}")
    output = BytesIO()
    image.save(output, format="JPEG", quality=90, optimize=True)
    return output.getvalue()


def build_benchmark_payloads(
    archive_path: Path,
    manifest: dict[str, Any],
    ood_dir: Path,
) -> list[dict[str, Any]]:
    """Build real and transformed cases while keeping raw bytes transient."""
    with zipfile.ZipFile(archive_path) as archive:
        raw_cache: dict[str, bytes] = {}

        def member_is_eligible(member: str) -> bool:
            raw_bytes = raw_cache.setdefault(member, archive.read(member))
            try:
                validated = validate_chat_image_payload(
                    base64.b64encode(raw_bytes).decode("ascii"),
                    _mime_type(member),
                )
            except ValueError:
                return False
            return bool(validated.observation["usable_for_vision"])

        plant_cases = plantdoc_benchmark_cases(
            archive.namelist(), manifest, member_is_eligible
        )
        for case in plant_cases:
            member = case.pop("member")
            case["raw_bytes"] = raw_cache.setdefault(member, archive.read(member))
            case["mime_type"] = _mime_type(member)
            case["image_id"] = hashlib.sha256(case["raw_bytes"]).hexdigest()[:16]

    quality_cases: list[dict[str, Any]] = []
    for variant in manifest["quality_variants"]:
        candidates = [
            case for case in plant_cases
            if case["category"] == variant["source_category"]
        ]
        count = int(variant["count"])
        if len(candidates) < count:
            raise ValueError(
                f"quality variant {variant['id']} needs {count} source images"
            )
        for source in candidates[:count]:
            raw_bytes = make_quality_variant(source["raw_bytes"], variant)
            quality_cases.append({
                "case_id": f"quality-{variant['id']}-{source['case_id']}",
                "category": "quality",
                "variant": variant["id"],
                "expected_issue": variant["expected_issue"],
                "source_case_id": source["case_id"],
                "mime_type": "image/jpeg",
                "raw_bytes": raw_bytes,
                "image_id": hashlib.sha256(raw_bytes).hexdigest()[:16],
            })

    ood_cases: list[dict[str, Any]] = []
    for filename in manifest["ood"]["images"]:
        path = ood_dir / filename
        if not path.is_file():
            raise ValueError(
                f"OOD image missing: {path}; run vision_training/scripts/prepare_ood_eval.py"
            )
        raw_bytes = path.read_bytes()
        ood_cases.append({
            "case_id": f"ood-{Path(filename).stem}",
            "category": "ood",
            "source_file": filename,
            "mime_type": _mime_type(filename),
            "raw_bytes": raw_bytes,
            "image_id": hashlib.sha256(raw_bytes).hexdigest()[:16],
        })
    return [*plant_cases, *quality_cases, *ood_cases]


def benchmark_batches(
    payloads: list[dict[str, Any]], batch_size: int
) -> list[list[dict[str, Any]]]:
    """Batch at most two same-category images without changing case order."""
    if batch_size not in {1, 2}:
        raise ValueError("batch_size must be 1 or 2")
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for case in payloads:
        current_limit = (
            1 if current and current[0]["category"] == "ood" else batch_size
        )
        if current and (
            len(current) >= current_limit
            or current[0]["category"] != case["category"]
        ):
            batches.append(current)
            current = []
        current.append(case)
    if current:
        batches.append(current)
    return batches


def _is_tomato(candidate: Any) -> bool:
    value = " ".join(str(candidate or "").casefold().split())
    return "tomato" in value or "cà chua" in value


def _is_successful_analysis(vision: dict[str, Any], observation: dict[str, Any]) -> bool:
    """Only score provider behavior when a typed observation was produced."""
    return (
        vision.get("mode") == "typed_observations"
        and not vision.get("error")
        and bool(observation)
    )


def vision_enabled_for_eval(
    globally_enabled: bool, eval_user_email: str, test_user_emails: str
) -> bool:
    """Mirror production's global-or-allowlisted vision gate for the eval user."""
    if globally_enabled:
        return True
    allowed = {
        email.strip().casefold()
        for email in test_user_emails.split(",")
        if email.strip()
    }
    email = eval_user_email.strip().casefold()
    return bool(email and email in allowed)


def score_case(case: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    trace = response.get("trace") or {}
    vision = trace.get("vision") or {}
    observations = vision.get("visual_observations") or []
    case_image_id = case.get("image_id")
    observation = (
        next(
            (
                item for item in observations
                if item.get("image_id") == case_image_id
            ),
            {},
        )
        if case_image_id
        else (observations[0] if observations else {})
    )
    image_observations = vision.get("observations") or []
    image_observation = (
        next(
            (
                item for item in image_observations
                if item.get("image_id") == case_image_id
            ),
            {},
        )
        if case_image_id
        else (image_observations[0] if image_observations else {})
    )
    successful = _is_successful_analysis(vision, observation)
    relevance = observation.get("relevance")
    tomato_scope = _is_tomato(observation.get("crop_candidate"))
    symptom_count = len(observation.get("visible_symptoms") or [])
    category = case["category"]

    if category == "healthy":
        passed = successful and relevance == "agriculture_plant" and tomato_scope
    elif category == "look_alike":
        passed = (
            successful
            and relevance == "agriculture_plant"
            and tomato_scope
            and symptom_count > 0
        )
    elif category == "quality":
        passed = (
            vision.get("mode") == "validation_only"
            and vision.get("stop_reason") == "image_quality_insufficient"
            and case["expected_issue"] in (image_observation.get("quality_issues") or [])
            and not observations
        )
    elif category == "ood":
        passed = (
            successful
            and relevance == "out_of_domain"
            and vision.get("stop_reason") == "image_irrelevant"
        )
    else:
        raise ValueError(f"unsupported benchmark category: {category}")

    return {
        "case_id": case["case_id"],
        "category": category,
        "challenge_group": case.get("challenge_group"),
        "source_class": case.get("source_class"),
        "variant": case.get("variant"),
        "expected_issue": case.get("expected_issue"),
        "vision_mode": vision.get("mode"),
        "vision_error": vision.get("error"),
        "vision_stop_reason": vision.get("stop_reason"),
        "quality_issues": image_observation.get("quality_issues") or [],
        "relevance": relevance,
        "crop_candidate": observation.get("crop_candidate"),
        "confidence": observation.get("confidence"),
        "symptom_count": symptom_count,
        "successful_analysis": successful,
        "passed": passed,
    }


def _rate(results: list[dict[str, Any]], category: str) -> float:
    selected = [result for result in results if result["category"] == category]
    return sum(bool(result.get("passed")) for result in selected) / max(
        len(selected), 1
    )


def build_report(
    manifest: dict[str, Any], results: list[dict[str, Any]], expected_size: int
) -> dict[str, Any]:
    provider_cases = [
        result for result in results if result["category"] != "quality"
    ]
    metrics = {
        "provider_analysis_rate": sum(
            bool(result.get("successful_analysis")) for result in provider_cases
        ) / max(len(provider_cases), 1),
        "healthy_tomato_scope_rate": _rate(results, "healthy"),
        "look_alike_observation_rate": _rate(results, "look_alike"),
        "quality_rejection_rate": _rate(results, "quality"),
        "ood_rejection_rate": _rate(results, "ood"),
    }
    thresholds = manifest["thresholds"]
    failed_gates = [
        metric for metric, threshold in thresholds.items()
        if metrics.get(metric, 0.0) < float(threshold)
    ]
    blockers = [f"metric_below_threshold:{metric}" for metric in failed_gates]
    if len(results) != expected_size:
        blockers.append("benchmark_sample_incomplete")
    return {
        "dataset": manifest["version"],
        "runtime_fingerprint": runtime_fingerprint(),
        "vision_model": model_name(ModelRole.VISION),
        "sample_size": len(results),
        "expected_sample_size": expected_size,
        "category_counts": {
            category: sum(result["category"] == category for result in results)
            for category in ("healthy", "look_alike", "quality", "ood")
        },
        "metrics": metrics,
        "thresholds": thresholds,
        "cases": results,
        "promotion_pass": not blockers,
        "promotion_blockers": blockers,
    }


def merge_case_results(
    ordered_case_ids: list[str],
    previous_results: list[dict[str, Any]],
    new_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Replace rerun cases and discard results no longer present in the manifest."""
    merged = {result["case_id"]: result for result in previous_results}
    merged.update({result["case_id"]: result for result in new_results})
    return [merged[case_id] for case_id in ordered_case_ids if case_id in merged]


async def run(args: argparse.Namespace) -> dict[str, Any]:
    if not args.allow_provider_calls:
        raise RuntimeError("pass --allow-provider-calls to acknowledge Gemini API usage")
    if not vision_enabled_for_eval(
        settings.vision_analysis_enabled,
        settings.eval_user_email,
        settings.vision_test_user_emails,
    ):
        raise RuntimeError(
            "benchmark eval user must be enabled globally or listed in VISION_TEST_USER_EMAILS"
        )

    manifest = json.loads(args.benchmark_manifest.read_text(encoding="utf-8"))
    all_payloads = build_benchmark_payloads(args.archive, manifest, args.ood_dir)
    expected_size = len(all_payloads)
    ordered_case_ids = [case["case_id"] for case in all_payloads]
    previous_results: list[dict[str, Any]] = []
    if args.resume_from:
        previous_report = json.loads(args.resume_from.read_text(encoding="utf-8"))
        if previous_report.get("dataset") != manifest["version"]:
            raise ValueError("resume report dataset version does not match manifest")
        previous_results = previous_report.get("cases") or []
    previous_by_id = {result["case_id"]: result for result in previous_results}

    selected_ids = set(args.case_ids or [])
    if selected_ids:
        unknown = selected_ids.difference(ordered_case_ids)
        if unknown:
            raise ValueError(f"unknown benchmark case ids: {sorted(unknown)}")
        payloads = [case for case in all_payloads if case["case_id"] in selected_ids]
    elif args.resume_from:
        payloads = [
            case for case in all_payloads
            if case["case_id"] not in previous_by_id
            or not previous_by_id[case["case_id"]].get("passed")
        ]
    else:
        payloads = all_payloads
    if args.case_limit is not None:
        payloads = payloads[:args.case_limit]
    batches = benchmark_batches(payloads, args.batch_size)

    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=args.timeout) as client:
        token = await get_supabase_token(client)
        for index, batch in enumerate(batches):
            try:
                response = await invoke_production_chat(
                    client,
                    token,
                    IMAGE_QUESTION,
                    images=[
                        {
                            "mime_type": case["mime_type"],
                            "data_base64": base64.b64encode(
                                case["raw_bytes"]
                            ).decode("ascii"),
                        }
                        for case in batch
                    ],
                )
                results.extend(score_case(case, response) for case in batch)
            except (httpx.HTTPError, ValueError) as exc:
                results.extend(
                    {
                        "case_id": case["case_id"],
                        "category": case["category"],
                        "request_error": type(exc).__name__,
                        "successful_analysis": False,
                        "passed": False,
                    }
                    for case in batch
                )
            finally:
                for case in batch:
                    case.pop("raw_bytes", None)
            if index + 1 < len(batches):
                await asyncio.sleep(args.delay)

    if previous_results:
        results = merge_case_results(ordered_case_ids, previous_results, results)
    report = build_report(manifest, results, expected_size)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--ood-dir", type=Path, default=DEFAULT_OOD_DIR)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--case-limit", type=int)
    parser.add_argument("--case-id", dest="case_ids", action="append")
    parser.add_argument("--resume-from", type=Path)
    parser.add_argument("--batch-size", type=int, choices=(1, 2), default=2)
    parser.add_argument("--delay", type=float, default=7.0)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--allow-provider-calls", action="store_true")
    args = parser.parse_args()
    report = asyncio.run(run(args))
    print(json.dumps(
        {key: value for key, value in report.items() if key != "cases"},
        ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
