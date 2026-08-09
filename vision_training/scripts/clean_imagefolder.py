"""Decode, standardize, and quality-flag an approved image manifest offline."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import warnings
from collections import Counter
from pathlib import Path


def canonicalize_image(image, max_side: int, min_side: int) -> tuple[bytes, list[str]]:
    from PIL import Image, ImageFilter, ImageOps, ImageStat

    image.load()
    image = ImageOps.exif_transpose(image).convert("RGB")
    width, height = image.size
    if min(width, height) < min_side:
        raise ValueError(f"image is smaller than {min_side}px on its shortest side")
    if width * height > 25_000_000:
        raise ValueError("image exceeds 25 megapixels")
    image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    grayscale = image.convert("L")
    brightness = ImageStat.Stat(grayscale).mean[0]
    edge_variance = ImageStat.Stat(grayscale.filter(ImageFilter.FIND_EDGES)).var[0]
    flags: list[str] = []
    if brightness < 25 or brightness > 230:
        flags.append("extreme_brightness")
    if edge_variance < 20:
        flags.append("low_detail")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=95, subsampling=0, optimize=False)
    return buffer.getvalue(), flags


def canonicalize(source: Path, max_side: int, min_side: int) -> tuple[bytes, list[str]]:
    from PIL import Image

    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(source) as image:
            return canonicalize_image(image, max_side, min_side)


def clean_manifest(
    input_manifest: Path,
    output_dir: Path,
    max_side: int,
    min_side: int,
    reject_quality_flags: set[str] | None = None,
) -> dict:
    reject_quality_flags = reject_quality_flags or set()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output_dir must be empty to avoid overwriting a cleaned dataset")
    with input_manifest.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    fieldnames = ["image_path", "split", "label", "capture_group", "source", "consent_status", "notes"]
    output_rows: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = []
    seen: dict[str, tuple[str, str]] = {}
    quality_flags: Counter[str] = Counter()
    for row in rows:
        source = Path(row["image_path"])
        try:
            payload, flags = canonicalize(source, max_side, min_side)
        except Exception as error:
            rejected.append({"image_path": str(source), "reason": str(error)})
            continue
        rejected_flags = sorted(reject_quality_flags.intersection(flags))
        if rejected_flags:
            rejected.append(
                {
                    "image_path": str(source),
                    "reason": f"reviewed_quality_rejection:{','.join(rejected_flags)}",
                }
            )
            continue
        digest = hashlib.sha256(payload).hexdigest()
        existing = seen.get(digest)
        if existing is not None:
            existing_split, existing_label = existing
            if existing_label != row["label"]:
                raise ValueError("canonical duplicate has conflicting labels")
            rejected.append({"image_path": str(source), "reason": f"canonical_duplicate_of_{existing_split}"})
            continue
        seen[digest] = (row["split"], row["label"])
        destination = output_dir / row["split"] / row["label"] / f"{digest}.jpg"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        flags_text = ",".join(flags) if flags else "none"
        quality_flags.update(flags)
        output_rows.append(
            {
                **{name: row.get(name, "") for name in fieldnames if name != "image_path" and name != "notes"},
                "image_path": str(destination),
                "notes": f"canonical_rgb_jpeg; quality_flags={flags_text}",
            }
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "manifest.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)
    report = {
        "input_images": len(rows),
        "kept_images": len(output_rows),
        "rejected_images": len(rejected),
        "quality_flags": dict(sorted(quality_flags.items())),
        "rejections": rejected,
        "canonical_format": "RGB JPEG quality=95",
        "max_side": max_side,
        "min_side": min_side,
        "rejected_quality_flags": sorted(reject_quality_flags),
    }
    (output_dir / "cleaning_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-side", type=int, default=1024)
    parser.add_argument("--min-side", type=int, default=64)
    parser.add_argument("--reject-quality-flag", action="append", default=[])
    args = parser.parse_args()
    print(
        json.dumps(
            clean_manifest(
                args.manifest,
                args.output_dir,
                args.max_side,
                args.min_side,
                set(args.reject_quality_flag),
            ),
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
