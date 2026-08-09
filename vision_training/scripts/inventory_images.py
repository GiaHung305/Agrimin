"""Inventory image files, remove exact duplicates, and emit a training manifest."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def inventory(root: Path, source_id: str, label_map: dict[str, str]) -> tuple[list[dict[str, str]], list[str]]:
    rows: list[dict[str, str]] = []
    duplicates: list[str] = []
    hashes: set[str] = set()
    for path in sorted(root.rglob("*")):
        if path.suffix.casefold() not in IMAGE_SUFFIXES:
            continue
        source_label = path.parent.name
        label = label_map.get(source_label)
        if label is None:
            continue
        digest = sha256_file(path)
        if digest in hashes:
            duplicates.append(str(path))
            continue
        hashes.add(digest)
        rows.append({
            "image_path": str(path),
            "split": "unassigned",
            "label": label,
            "capture_group": f"{source_id}:{digest}",
            "source": source_id,
            "consent_status": "public_license_reviewed",
            "notes": "capture session unknown; exact duplicates removed by SHA-256",
        })
    return rows, duplicates


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--label-map", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    label_map = json.loads(args.label_map.read_text(encoding="utf-8"))
    rows, duplicates = inventory(args.root, args.source_id, label_map)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["image_path", "split", "label", "capture_group", "source", "consent_status", "notes"])
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"images": len(rows), "exact_duplicates": len(duplicates)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
