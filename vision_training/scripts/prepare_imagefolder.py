"""Prepare a reproducible ImageFolder split from an approved classified source."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

from vision_training.scripts.inventory_images import IMAGE_SUFFIXES, sha256_file


def is_test_member(digest: str, test_fraction: float) -> bool:
    return int(digest[:16], 16) < test_fraction * (16**16)


def link_or_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
    except OSError:
        destination.write_bytes(source.read_bytes())


def prepare(
    source_root: Path,
    output_dir: Path,
    source_id: str,
    label_map: dict[str, str],
    test_fraction: float,
) -> tuple[list[dict[str, str]], list[str]]:
    if not 0 < test_fraction < 1:
        raise ValueError("test_fraction must be between 0 and 1")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output_dir must be empty to avoid overwriting a prepared dataset")
    rows: list[dict[str, str]] = []
    duplicates: list[str] = []
    seen: dict[str, str] = {}
    # Prioritise the source validation split so an exact duplicate cannot leak from train.
    for source_split in ("val", "train"):
        split_dir = source_root / source_split
        if not split_dir.is_dir():
            raise ValueError(f"missing expected source split: {split_dir}")
        for path in sorted(split_dir.rglob("*")):
            if path.suffix.casefold() not in IMAGE_SUFFIXES:
                continue
            source_label = path.relative_to(split_dir).parts[0]
            label = label_map.get(source_label)
            if label is None:
                continue
            digest = sha256_file(path)
            existing_label = seen.get(digest)
            if existing_label is not None:
                if existing_label != label:
                    raise ValueError("identical image bytes map to conflicting labels")
                duplicates.append(str(path))
                continue
            seen[digest] = label
            split = "val" if source_split == "val" else ("test" if is_test_member(digest, test_fraction) else "train")
            destination = output_dir / split / label / f"{digest}{path.suffix.casefold()}"
            link_or_copy(path, destination)
            rows.append(
                {
                    "image_path": str(destination),
                    "split": split,
                    "label": label,
                    "capture_group": f"{source_id}:{digest}",
                    "source": source_id,
                    "consent_status": "public_license_reviewed",
                    "notes": "source split preserved for val; train/test assigned by SHA-256; exact duplicates removed",
                }
            )
    return rows, duplicates


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--label-map", type=Path, required=True)
    parser.add_argument("--test-fraction", type=float, default=0.1)
    args = parser.parse_args()
    label_map = json.loads(args.label_map.read_text(encoding="utf-8"))
    rows, duplicates = prepare(
        args.source_root, args.output_dir, args.source_id, label_map, args.test_fraction
    )
    manifest_path = args.output_dir / "manifest.csv"
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["image_path", "split", "label", "capture_group", "source", "consent_status", "notes"])
        writer.writeheader()
        writer.writerows(rows)
    print(
        json.dumps(
            {"images": len(rows), "exact_duplicates": len(duplicates), "splits": Counter(row["split"] for row in rows)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
