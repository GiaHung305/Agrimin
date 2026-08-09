"""Evaluate a reviewed checkpoint on the held-out test split."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from vision_training.scripts.train import _load_dependencies, _model


def promotion_decision(config: dict, accuracy: float, macro_f1: float, low_confidence_rate: float) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if accuracy < float(config["promotion_min_test_accuracy"]):
        failures.append("test_accuracy_below_threshold")
    if macro_f1 < float(config["promotion_min_macro_f1"]):
        failures.append("macro_f1_below_threshold")
    if low_confidence_rate > float(config["promotion_max_low_confidence_rate"]):
        failures.append("low_confidence_rate_above_threshold")
    return not failures, failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    _, torch, nn, _, DataLoader, _, datasets, models, transforms = _load_dependencies()
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    config = checkpoint["config"]
    labels = checkpoint["labels"]
    transform = transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(int(config["input_size"])),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    test_dataset = datasets.ImageFolder(args.data_dir / "test", transform)
    if test_dataset.classes != labels:
        raise ValueError("Test folder class order does not match checkpoint labels")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, _ = _model(models, nn, len(labels), backbone=config["backbone"], pretrained=False)
    model.load_state_dict(checkpoint["state_dict"])
    model.to(device).eval()
    predictions: list[int] = []
    targets: list[int] = []
    confidences: list[float] = []
    with torch.no_grad():
        for images, batch_targets in DataLoader(test_dataset, batch_size=32, shuffle=False):
            images = images.to(device)
            probabilities = torch.softmax(model(images), dim=1)
            batch_confidences, batch_predictions = probabilities.max(dim=1)
            predictions.extend(batch_predictions.tolist())
            targets.extend(batch_targets.tolist())
            confidences.extend(batch_confidences.tolist())

    from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

    threshold = float(config["review_min_confidence"])
    accuracy = float(accuracy_score(targets, predictions))
    classification = classification_report(
        targets, predictions, labels=list(range(len(labels))), target_names=labels, output_dict=True, zero_division=0,
    )
    low_confidence_rate = sum(value < threshold for value in confidences) / max(len(confidences), 1)
    promotion_pass, promotion_failures = promotion_decision(
        config, accuracy, float(classification["macro avg"]["f1-score"]), low_confidence_rate
    )
    report = {
        "model_version": config["model_version"],
        "labels": labels,
        "accuracy": accuracy,
        "low_confidence_rate": low_confidence_rate,
        "review_min_confidence": threshold,
        "classification_report": classification,
        "confusion_matrix": confusion_matrix(targets, predictions, labels=list(range(len(labels)))).tolist(),
        "dataset_benchmark_gate_pass": promotion_pass,
        "dataset_benchmark_failures": promotion_failures,
        "production_promotion_pass": False,
        "production_blockers": [
            "independent_real_world_evaluation_missing",
            "out_of_domain_abstention_evaluation_missing",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("model_version", "accuracy", "low_confidence_rate", "dataset_benchmark_gate_pass", "production_promotion_pass", "production_blockers")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
