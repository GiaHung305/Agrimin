"""Prepare the official PlantVillage tomato subset with leaf-group isolation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from vision_training.scripts.clean_imagefolder import canonicalize_image


def validation_leaf_ids(records: list[tuple[str, str]], fraction: float, seed: int) -> set[str]:
    if not 0 < fraction < 1:
        raise ValueError("validation fraction must be between 0 and 1")
    by_label: dict[str, set[str]] = defaultdict(set)
    for leaf_id, label in records:
        by_label[label].add(leaf_id)
    selected: set[str] = set()
    for leaf_ids in by_label.values():
        ordered = sorted(
            leaf_ids,
            key=lambda value: hashlib.sha256(f"{seed}:{value}".encode()).hexdigest(),
        )
        count = max(1, round(len(ordered) * fraction))
        selected.update(ordered[:count])
    return selected


def lookup_leaf_id(file_path: str, class_name: str, leaf_map: dict[str, list[str]]) -> str:
    file_name = file_path.rsplit("/", 1)[-1]
    image_identifier = file_name.replace("_final_masked", "")
    if "___" in image_identifier:
        image_identifier = image_identifier.split("___")[-1]
    image_identifier = image_identifier.split("copy")[0]
    for suffix in (".jpg", ".JPG", ".png", ".PNG"):
        image_identifier = image_identifier.replace(suffix, "")
    image_identifier = image_identifier.strip()
    suggestions = leaf_map.get(image_identifier.casefold(), [])
    if len(suggestions) == 1:
        return suggestions[0]
    for suggestion in suggestions:
        if class_name in suggestion:
            return suggestion
    return f"fallback_{image_identifier}"


def prepare(
    dataset_name: str,
    dataset_config: str,
    revision: str,
    output_dir: Path,
    label_map: dict[str, str],
    validation_fraction: float,
    seed: int,
) -> dict:
    from huggingface_hub import hf_hub_download
    from PIL import Image

    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output_dir must be empty to avoid overwriting prepared data")
    downloaded = {
        name: Path(
            hf_hub_download(dataset_name, name, repo_type="dataset", revision=revision)
        )
        for name in (
            "data.zip",
            "leaf_grouping/leaf-map.json",
            f"splits/{dataset_config}_train.txt",
            f"splits/{dataset_config}_test.txt",
        )
    }
    leaf_map = json.loads(downloaded["leaf_grouping/leaf-map.json"].read_text(encoding="utf-8"))
    records_by_source_split: dict[str, list[tuple[str, str, str]]] = {}
    for source_split in ("train", "test"):
        split_path = downloaded[f"splits/{dataset_config}_{source_split}.txt"]
        records: list[tuple[str, str, str]] = []
        for relative_path in split_path.read_text(encoding="utf-8").splitlines():
            parts = relative_path.strip().split("/")
            if len(parts) < 4 or not parts[2].startswith("Tomato___"):
                continue
            source_label = parts[2]
            label = label_map.get(source_label)
            if label is None:
                raise ValueError(f"unmapped tomato label: {source_label}")
            records.append((relative_path.strip(), label, lookup_leaf_id(relative_path, source_label, leaf_map)))
        records_by_source_split[source_split] = records
    train_records = [(leaf_id, label) for _, label, leaf_id in records_by_source_split["train"]]
    val_leaf_ids = validation_leaf_ids(train_records, validation_fraction, seed)

    fieldnames = ["image_path", "split", "label", "capture_group", "source", "consent_status", "notes"]
    rows: list[dict[str, str]] = []
    seen_hashes: dict[str, tuple[str, str]] = {}
    duplicates = 0
    cross_split_duplicates = 0
    quality_flags: Counter[str] = Counter()
    with zipfile.ZipFile(downloaded["data.zip"]) as archive:
        members: dict[str, str] = {}
        for name in archive.namelist():
            raw_index = name.find("raw/")
            if raw_index >= 0:
                members[name[raw_index:]] = name
        for source_split in ("train", "test"):
            for relative_path, label, leaf_id in records_by_source_split[source_split]:
                member = members.get(relative_path)
                if member is None:
                    raise ValueError(f"archive is missing split member: {relative_path}")
                split = "test" if source_split == "test" else ("val" if leaf_id in val_leaf_ids else "train")
                with archive.open(member) as stream, Image.open(stream) as image:
                    payload, flags = canonicalize_image(image, max_side=1024, min_side=64)
                digest = hashlib.sha256(payload).hexdigest()
                existing = seen_hashes.get(digest)
                if existing is not None:
                    existing_split, existing_label = existing
                    if existing_label != label:
                        raise ValueError("canonical duplicate has conflicting labels")
                    if existing_split != split:
                        cross_split_duplicates += 1
                    duplicates += 1
                    continue
                seen_hashes[digest] = (split, label)
                destination = output_dir / split / label / f"{digest}.jpg"
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(payload)
                quality_flags.update(flags)
                rows.append(
                    {
                        "image_path": str(destination),
                        "split": split,
                        "label": label,
                        "capture_group": f"plantvillage_official:{leaf_id}",
                        "source": "plantvillage_official",
                        "consent_status": "public_license_reviewed",
                        "notes": f"official leaf-group split; canonical_rgb_jpeg; quality_flags={','.join(flags) if flags else 'none'}",
                    }
                )
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "manifest.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    report = {
        "dataset": dataset_name,
        "configuration": dataset_config,
        "revision": revision,
        "images": len(rows),
        "exact_duplicates": duplicates,
        "cross_split_duplicates_removed": cross_split_duplicates,
        "splits": dict(sorted(Counter(row["split"] for row in rows).items())),
        "labels": dict(sorted(Counter(row["label"] for row in rows).items())),
        "quality_flags": dict(sorted(quality_flags.items())),
        "split_unit": "leaf_id",
        "license_status": "CC-BY-SA-3.0",
        "production_eligible": False,
    }
    (output_dir / "preparation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="mohanty/PlantVillage")
    parser.add_argument("--dataset-config", default="color")
    parser.add_argument("--revision", default="9e97599868962bd0079b8db4b7f1efa9185fa1e7")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--label-map", type=Path, required=True)
    parser.add_argument("--validation-fraction", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    label_map = json.loads(args.label_map.read_text(encoding="utf-8"))
    report = prepare(
        args.dataset,
        args.dataset_config,
        args.revision,
        args.output_dir,
        label_map,
        args.validation_fraction,
        args.seed,
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
