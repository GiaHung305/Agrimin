"""Extract a small provenance-tracked OOD image pack from an approved archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, UnidentifiedImageError


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def prepare_ood_eval(archive_path: Path, manifest_path: Path, output_dir: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("intended_use") != "vision_out_of_domain_evaluation_only":
        raise ValueError("manifest is not approved for OOD vision evaluation")
    archive_sha256 = sha256_file(archive_path)
    if archive_sha256 != manifest["archive_sha256"]:
        raise ValueError("archive SHA-256 does not match the pinned OOD manifest")

    output_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[dict] = []
    with zipfile.ZipFile(archive_path) as archive:
        available = set(archive.namelist())
        for item in manifest["images"]:
            member = item["archive_member"]
            if member not in available:
                raise ValueError(f"archive member is missing: {member}")
            payload = archive.read(member)
            payload_sha256 = sha256_bytes(payload)
            if payload_sha256 != item["sha256"]:
                raise ValueError(f"image SHA-256 does not match manifest: {member}")
            target = output_dir / item["output_file"]
            target.write_bytes(payload)
            try:
                with Image.open(target) as image:
                    image.verify()
                with Image.open(target) as image:
                    width, height = image.size
                    image_format = image.format
            except (UnidentifiedImageError, OSError) as exc:
                target.unlink(missing_ok=True)
                raise ValueError(f"invalid image extracted from {member}") from exc
            extracted.append({
                **item,
                "sha256": payload_sha256,
                "bytes": len(payload),
                "width": width,
                "height": height,
                "format": image_format,
            })

    provenance = {
        "schema_version": "agrimind-ood-provenance-v1",
        "dataset_version": manifest["version"],
        "source_id": manifest["source_id"],
        "source_revision": manifest["source_revision"],
        "archive_file": archive_path.name,
        "archive_sha256": archive_sha256,
        "prepared_at": datetime.now(UTC).isoformat(),
        "images": extracted,
    }
    (output_dir / "provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return provenance


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--allow-extract", action="store_true")
    args = parser.parse_args()
    if not args.allow_extract:
        raise SystemExit("Refusing extraction without --allow-extract")
    report = prepare_ood_eval(args.archive, args.manifest, args.output_dir)
    print(json.dumps({"dataset_version": report["dataset_version"], "images": len(report["images"])}))


if __name__ == "__main__":
    main()
