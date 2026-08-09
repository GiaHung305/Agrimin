"""Download an explicitly approved public dataset with provenance metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path


MAX_ARCHIVE_BYTES = 3 * 1024 * 1024 * 1024


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_source(registry_path: Path, source_id: str) -> dict:
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for source in registry["sources"]:
        if source["id"] == source_id:
            return source
    raise ValueError(f"unknown source id: {source_id}")


def download(source: dict, output_dir: Path) -> Path:
    if source.get("kaggle_dataset"):
        return download_from_kaggle(source, output_dir)
    if not source.get("download_url"):
        raise ValueError(f"source {source['id']} has no approved download URL")
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"{source['id']}.zip"
    partial_path = archive_path.with_suffix(".part")
    request = urllib.request.Request(source["download_url"], headers={"User-Agent": "AgriMind-dataset-prep/1.0"})
    hasher = hashlib.sha256()
    downloaded = 0
    try:
        with urllib.request.urlopen(request, timeout=60) as response, partial_path.open("wb") as target:
            while chunk := response.read(1024 * 1024):
                downloaded += len(chunk)
                if downloaded > MAX_ARCHIVE_BYTES:
                    raise ValueError("dataset archive exceeds configured safety limit")
                hasher.update(chunk)
                target.write(chunk)
        partial_path.replace(archive_path)
    except Exception:
        partial_path.unlink(missing_ok=True)
        raise
    provenance = {
        "source_id": source["id"],
        "reference_url": source["reference_url"],
        "download_url": source["download_url"],
        "license_status": source["license_status"],
        "production_eligible": source["production_eligible"],
        "downloaded_at": datetime.now(UTC).isoformat(),
        "archive_file": archive_path.name,
        "sha256": hasher.hexdigest(),
        "bytes": downloaded,
    }
    (output_dir / f"{source['id']}.provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return archive_path


def download_from_kaggle(source: dict, output_dir: Path) -> Path:
    """Download through the local Kaggle CLI without reading credentials ourselves."""
    executable_name = "kaggle.exe" if sys.platform == "win32" else "kaggle"
    venv_executable = Path(sys.executable).with_name(executable_name)
    executable = str(venv_executable) if venv_executable.is_file() else shutil.which("kaggle")
    if executable is None:
        raise RuntimeError(
            "Kaggle CLI was not found. Install vision_training requirements, then retry."
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    before = {path.resolve() for path in output_dir.glob("*.zip")}
    command = [
        executable,
        "datasets",
        "download",
        "--dataset",
        source["kaggle_dataset"],
        "--path",
        str(output_dir),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(
            "Kaggle CLI download failed. Confirm the local Kaggle token is valid and has access; "
            "the credential was not read or logged by this script."
        )
    archives = [path for path in output_dir.glob("*.zip") if path.resolve() not in before]
    if len(archives) != 1:
        raise RuntimeError("Kaggle CLI did not produce exactly one new ZIP archive")
    archive_path = archives[0]
    if archive_path.stat().st_size > MAX_ARCHIVE_BYTES:
        archive_path.unlink(missing_ok=True)
        raise ValueError("dataset archive exceeds configured safety limit")
    provenance = {
        "source_id": source["id"],
        "reference_url": source["reference_url"],
        "kaggle_dataset": source["kaggle_dataset"],
        "license_status": source["license_status"],
        "production_eligible": source["production_eligible"],
        "downloaded_at": datetime.now(UTC).isoformat(),
        "archive_file": archive_path.name,
        "sha256": sha256_file(archive_path),
        "bytes": archive_path.stat().st_size,
    }
    (output_dir / f"{source['id']}.provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return archive_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument("--allow-research-source", action="store_true")
    args = parser.parse_args()
    if not args.allow_download:
        raise SystemExit("Refusing download without --allow-download")
    source = load_source(args.registry, args.source)
    if not source.get("production_eligible", False) and not args.allow_research_source:
        raise SystemExit("Source requires --allow-research-source after license review")
    print(download(source, args.output_dir))


if __name__ == "__main__":
    main()
