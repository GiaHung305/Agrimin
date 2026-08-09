"""Evaluate a frozen checkpoint on mapped field images plus balanced OOD images."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import zipfile
from collections import defaultdict
from pathlib import Path

from vision_training.scripts.train import _load_dependencies, _model


def archive_records(
    names: list[str],
    label_map: dict[str, str],
    source_splits: set[str] | None = None,
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str]]]:
    allowed_splits = source_splits or {"train", "test"}
    mapped: list[tuple[str, str, str]] = []
    ood: list[tuple[str, str]] = []
    for name in names:
        parts = name.split("/")
        if len(parts) != 4 or parts[1] not in allowed_splits or name.endswith("/"):
            continue
        source_class = parts[2]
        label = label_map.get(source_class)
        if label is not None:
            mapped.append((name, label, source_class))
        elif not source_class.casefold().startswith("tomato"):
            ood.append((name, source_class))
    return mapped, ood


def balanced_ood_sample(records: list[tuple[str, str]], limit: int) -> list[tuple[str, str]]:
    by_class: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for record in records:
        by_class[record[1]].append(record)
    if not by_class or limit <= 0:
        return []
    per_class = max(1, math.ceil(limit / len(by_class)))
    selected: list[tuple[str, str]] = []
    for source_class in sorted(by_class):
        ordered = sorted(by_class[source_class], key=lambda item: hashlib.sha256(item[0].encode()).hexdigest())
        selected.extend(ordered[:per_class])
    return sorted(selected, key=lambda item: hashlib.sha256(item[0].encode()).hexdigest())[:limit]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--label-map", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--source-split",
        choices=("train", "test", "all"),
        default="test",
        help="PlantDoc split to evaluate; test is held out from domain adaptation.",
    )
    parser.add_argument("--ood-limit", type=int, default=300)
    parser.add_argument("--min-field-accuracy", type=float, default=0.75)
    parser.add_argument("--min-field-macro-f1", type=float, default=0.70)
    parser.add_argument("--min-ood-rejection-rate", type=float, default=0.80)
    args = parser.parse_args()

    np, torch, nn, _, _, _, _, models, transforms = _load_dependencies()
    from PIL import Image
    from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    config = checkpoint["config"]
    labels = checkpoint["labels"]
    label_map = json.loads(args.label_map.read_text(encoding="utf-8"))
    unknown_labels = sorted(set(label_map.values()) - set(labels))
    if unknown_labels:
        raise ValueError(f"external mapping contains labels absent from checkpoint: {unknown_labels}")
    transform = transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(int(config["input_size"])),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, _ = _model(models, nn, len(labels), backbone=config["backbone"], pretrained=False)
    model.load_state_dict(checkpoint["state_dict"])
    model.to(device).eval()
    threshold = float(config["review_min_confidence"])

    with zipfile.ZipFile(args.archive) as archive:
        source_splits = {"train", "test"} if args.source_split == "all" else {args.source_split}
        mapped, ood = archive_records(archive.namelist(), label_map, source_splits)
        selected_ood = balanced_ood_sample(ood, args.ood_limit)
        items = [(name, label, False, source_class) for name, label, source_class in mapped]
        items.extend((name, None, True, source_class) for name, source_class in selected_ood)
        predictions: list[int] = []
        confidences: list[float] = []
        targets: list[int | None] = []
        is_ood_values: list[bool] = []
        source_classes: list[str] = []
        invalid_images: list[str] = []
        duplicate_images = 0
        seen_hashes: set[str] = set()
        batch_tensors = []
        batch_metadata: list[tuple[int | None, bool, str]] = []

        def flush() -> None:
            if not batch_tensors:
                return
            images = torch.stack(batch_tensors).to(device)
            with torch.no_grad():
                probabilities = torch.softmax(model(images), dim=1)
            batch_confidences, batch_predictions = probabilities.max(dim=1)
            predictions.extend(batch_predictions.cpu().tolist())
            confidences.extend(batch_confidences.cpu().tolist())
            targets.extend(item[0] for item in batch_metadata)
            is_ood_values.extend(item[1] for item in batch_metadata)
            source_classes.extend(item[2] for item in batch_metadata)
            batch_tensors.clear()
            batch_metadata.clear()

        for member, expected_label, is_ood, source_class in items:
            payload = archive.read(member)
            digest = hashlib.sha256(payload).hexdigest()
            if digest in seen_hashes:
                duplicate_images += 1
                continue
            seen_hashes.add(digest)
            try:
                with Image.open(io.BytesIO(payload)) as image:
                    tensor = transform(image.convert("RGB"))
            except Exception:
                invalid_images.append(member)
                continue
            target = labels.index(expected_label) if expected_label is not None else None
            batch_tensors.append(tensor)
            batch_metadata.append((target, is_ood, source_class))
            if len(batch_tensors) >= 32:
                flush()
        flush()

    field_indices = [index for index, value in enumerate(is_ood_values) if not value]
    ood_indices = [index for index, value in enumerate(is_ood_values) if value]
    field_targets = [targets[index] for index in field_indices]
    field_predictions = [predictions[index] for index in field_indices]
    supported_label_indices = sorted(set(int(value) for value in field_targets if value is not None))
    field_accuracy = float(accuracy_score(field_targets, field_predictions))
    classification = classification_report(
        field_targets,
        field_predictions,
        labels=supported_label_indices,
        target_names=[labels[index] for index in supported_label_indices],
        output_dict=True,
        zero_division=0,
    )
    field_macro_f1 = float(classification["macro avg"]["f1-score"])
    field_low_confidence_rate = sum(confidences[index] < threshold for index in field_indices) / max(len(field_indices), 1)
    ood_label = config.get("ood_label")
    ood_index = labels.index(ood_label) if ood_label in labels else None
    ood_rejections = [
        confidences[index] < threshold or (ood_index is not None and predictions[index] == ood_index)
        for index in ood_indices
    ]
    ood_rejection_rate = sum(ood_rejections) / max(len(ood_indices), 1)
    failures: list[str] = []
    if field_accuracy < args.min_field_accuracy:
        failures.append("field_accuracy_below_threshold")
    if field_macro_f1 < args.min_field_macro_f1:
        failures.append("field_macro_f1_below_threshold")
    if ood_rejection_rate < args.min_ood_rejection_rate:
        failures.append("ood_rejection_rate_below_threshold")
    report = {
        "model_version": config["model_version"],
        "source": "plantdoc_field_eval",
        "source_split": args.source_split,
        "field_images": len(field_indices),
        "ood_images": len(ood_indices),
        "invalid_images": invalid_images,
        "exact_duplicates_removed": duplicate_images,
        "field_accuracy": field_accuracy,
        "field_macro_f1": field_macro_f1,
        "field_low_confidence_rate": field_low_confidence_rate,
        "ood_rejection_rate": ood_rejection_rate,
        "ood_label": ood_label,
        "explicit_ood_predictions": sum(
            predictions[index] == ood_index for index in ood_indices
        ) if ood_index is not None else 0,
        "review_min_confidence": threshold,
        "classification_report": classification,
        "confusion_matrix": confusion_matrix(field_targets, field_predictions, labels=list(range(len(labels)))).tolist(),
        "external_benchmark_gate_pass": not failures,
        "external_benchmark_failures": failures,
        "production_promotion_pass": False,
        "production_blockers": failures or ["controlled_feature_flag_rollout_not_completed"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("field_images", "ood_images", "field_accuracy", "field_macro_f1", "field_low_confidence_rate", "ood_rejection_rate", "external_benchmark_gate_pass", "external_benchmark_failures")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
