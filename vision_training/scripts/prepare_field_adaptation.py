"""Build a leak-resistant PlantVillage + PlantDoc-train adaptation dataset."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, ImageOps

from vision_training.scripts.inventory_images import IMAGE_SUFFIXES, sha256_file


def _link_or_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
    except OSError:
        destination.write_bytes(source.read_bytes())


def field_validation_members(
    records: list[tuple[str, str, str]], fraction: float, seed: int
) -> set[str]:
    if not 0 < fraction < 1:
        raise ValueError("field validation fraction must be between 0 and 1")
    by_label: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for record in records:
        by_label[record[1]].append(record)
    selected: set[str] = set()
    for label, items in sorted(by_label.items()):
        ordered = sorted(
            items,
            key=lambda item: hashlib.sha256(f"{seed}:{label}:{item[2]}".encode()).hexdigest(),
        )
        validation_count = max(1, round(len(ordered) * fraction))
        if len(ordered) > 1:
            validation_count = min(validation_count, len(ordered) - 1)
        selected.update(item[0] for item in ordered[:validation_count])
    return selected


def _archive_records(
    archive: zipfile.ZipFile, label_map: dict[str, str], source_split: str
) -> list[tuple[str, str, str]]:
    records: list[tuple[str, str, str]] = []
    for member in archive.namelist():
        parts = member.split("/")
        if len(parts) != 4 or parts[1] != source_split or member.endswith("/"):
            continue
        label = label_map.get(parts[2])
        if label is not None:
            records.append((member, label, hashlib.sha256(archive.read(member)).hexdigest()))
    return records


def prepare(
    base_dir: Path,
    archive_path: Path,
    output_dir: Path,
    label_map: dict[str, str],
    field_val_fraction: float = 0.15,
    seed: int = 42,
    field_validation_only: bool = False,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output_dir must be empty to avoid overwriting a prepared dataset")
    rows: list[dict[str, str]] = []
    counts: Counter[str] = Counter()
    seen: dict[str, str] = {}

    with zipfile.ZipFile(archive_path) as archive:
        heldout = _archive_records(archive, label_map, "test")
        heldout_hashes = {digest for _, _, digest in heldout}
        all_field_records = _archive_records(archive, label_map, "train")
        field_records = [record for record in all_field_records if record[2] not in heldout_hashes]
        counts["field_test_exact_duplicates_excluded"] = len(all_field_records) - len(field_records)
        field_val = field_validation_members(field_records, field_val_fraction, seed)

        labels = sorted(set(label_map.values()))
        for split in ("train", "val"):
            for label in labels:
                (output_dir / split / label).mkdir(parents=True, exist_ok=True)

        for source_split in ("val", "train"):
            if field_validation_only and source_split == "val":
                counts["base_val_excluded_from_field_validation"] += sum(
                    1 for path in (base_dir / source_split).rglob("*")
                    if path.suffix.casefold() in IMAGE_SUFFIXES
                )
                continue
            split_dir = base_dir / source_split
            if not split_dir.is_dir():
                raise ValueError(f"missing base split: {split_dir}")
            for source in sorted(split_dir.rglob("*")):
                if source.suffix.casefold() not in IMAGE_SUFFIXES:
                    continue
                label = source.relative_to(split_dir).parts[0]
                digest = sha256_file(source)
                if digest in heldout_hashes:
                    counts["base_test_exact_duplicates_excluded"] += 1
                    continue
                if digest in seen:
                    if seen[digest] != label:
                        raise ValueError("identical base image bytes map to conflicting labels")
                    counts["base_exact_duplicates_excluded"] += 1
                    continue
                seen[digest] = label
                destination = output_dir / source_split / label / f"base_{digest}{source.suffix.casefold()}"
                _link_or_copy(source, destination)
                rows.append({
                    "image_path": str(destination), "split": source_split, "label": label,
                    "capture_group": f"plantvillage:{digest}", "source": "plantvillage_hf",
                    "consent_status": "public_license_reviewed", "notes": "base domain",
                })
                counts[f"base_{source_split}"] += 1

        for member, label, digest in field_records:
            if digest in seen:
                if seen[digest] != label:
                    raise ValueError("identical cross-source image bytes map to conflicting labels")
                counts["cross_source_exact_duplicates_excluded"] += 1
                continue
            seen[digest] = label
            split = "val" if member in field_val else "train"
            try:
                with Image.open(io.BytesIO(archive.read(member))) as image:
                    canonical = ImageOps.exif_transpose(image).convert("RGB")
                    buffer = io.BytesIO()
                    canonical.save(buffer, format="JPEG", quality=92, optimize=True)
            except Exception:
                counts["invalid_field_images_excluded"] += 1
                continue
            destination = output_dir / split / label / f"field_{digest}.jpg"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(buffer.getvalue())
            rows.append({
                "image_path": str(destination), "split": split, "label": label,
                "capture_group": f"plantdoc:{digest}", "source": "plantdoc_train",
                "consent_status": "public_license_reviewed",
                "notes": "field adaptation only; PlantDoc test remains held out",
            })
            counts[f"field_{split}"] += 1
    return rows, dict(counts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--label-map", type=Path, required=True)
    parser.add_argument("--field-val-fraction", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--field-validation-only",
        action="store_true",
        help="Select checkpoints using only held-out PlantDoc-train images.",
    )
    args = parser.parse_args()
    label_map = json.loads(args.label_map.read_text(encoding="utf-8"))
    rows, counts = prepare(
        args.base_dir, args.archive, args.output_dir, label_map,
        args.field_val_fraction, args.seed, args.field_validation_only,
    )
    manifest = args.output_dir / "manifest.csv"
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["image_path", "split", "label", "capture_group", "source", "consent_status", "notes"],
        )
        writer.writeheader()
        writer.writerows(rows)
    (args.output_dir / "preparation_report.json").write_text(
        json.dumps({"images": len(rows), **counts}, indent=2), encoding="utf-8"
    )
    print(json.dumps({"images": len(rows), **counts}))


if __name__ == "__main__":
    main()
