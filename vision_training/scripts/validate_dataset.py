"""Validate a versioned image manifest before training a vision model.

The validator is dependency-free so it can run before installing PyTorch.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

REQUIRED_COLUMNS = {
    "image_path",
    "split",
    "label",
    "capture_group",
    "source",
    "consent_status",
}
VALID_SPLITS = {"train", "val", "test"}
VALID_CONSENT_STATUSES = {"verified", "public_license_reviewed"}


@dataclass(frozen=True)
class ValidationReport:
    model_version: str
    rows: int
    counts_by_split: dict[str, int]
    counts_by_label: dict[str, int]
    errors: list[str]
    warnings: list[str]


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise ValueError(f"manifest missing required columns: {sorted(missing)}")
        return [dict(row) for row in reader]


def validate_manifest(config: dict, rows: list[dict[str, str]], *, strict_minimum: bool) -> ValidationReport:
    labels = set(config["labels"])
    errors: list[str] = []
    warnings: list[str] = []
    image_paths: set[str] = set()
    group_splits: dict[str, set[str]] = defaultdict(set)
    split_counts: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()

    for index, row in enumerate(rows, start=2):
        image_path = row.get("image_path", "").strip()
        split = row.get("split", "").strip()
        label = row.get("label", "").strip()
        capture_group = row.get("capture_group", "").strip()
        consent_status = row.get("consent_status", "").strip()
        if not image_path:
            errors.append(f"row {index}: image_path is required")
            continue
        if image_path in image_paths:
            errors.append(f"row {index}: duplicate image_path {image_path}")
        image_paths.add(image_path)
        if split not in VALID_SPLITS:
            errors.append(f"row {index}: invalid split {split!r}")
        else:
            split_counts[split] += 1
        if label not in labels:
            errors.append(f"row {index}: label {label!r} is not in config")
        else:
            label_counts[label] += 1
        if not capture_group:
            errors.append(f"row {index}: capture_group is required")
        elif split in VALID_SPLITS:
            group_splits[capture_group].add(split)
        if consent_status not in VALID_CONSENT_STATUSES:
            errors.append(
                f"row {index}: consent_status must be one of "
                f"{sorted(VALID_CONSENT_STATUSES)}"
            )

    for capture_group, splits in group_splits.items():
        if len(splits) > 1:
            errors.append(
                f"capture_group {capture_group!r} spans splits {sorted(splits)}"
            )
    for split in sorted(VALID_SPLITS):
        if not split_counts[split]:
            errors.append(f"missing required split: {split}")

    minimum = int(config["min_prototype_images_per_label"])
    for label in sorted(labels):
        count = label_counts[label]
        if count < minimum:
            message = f"label {label!r} has {count} images; target is {minimum}"
            (errors if strict_minimum else warnings).append(message)

    return ValidationReport(
        model_version=str(config["model_version"]),
        rows=len(rows),
        counts_by_split=dict(sorted(split_counts.items())),
        counts_by_label=dict(sorted(label_counts.items())),
        errors=errors,
        warnings=warnings,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--strict-minimum", action="store_true")
    args = parser.parse_args()

    report = validate_manifest(
        load_config(args.config),
        load_manifest(args.manifest),
        strict_minimum=args.strict_minimum,
    )
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
