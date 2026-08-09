"""Fine-tune a lightweight tomato-observation classifier offline."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def _load_dependencies():
    import numpy as np
    import torch
    from torch import nn, optim
    from torch.utils.data import DataLoader, WeightedRandomSampler
    from torchvision import datasets, models, transforms

    return np, torch, nn, optim, DataLoader, WeightedRandomSampler, datasets, models, transforms


def _config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _model(models, nn, label_count: int, *, backbone: str = "mobilenet_v3_small", pretrained: bool = True):
    if backbone == "mobilenet_v3_small":
        weights = models.MobileNet_V3_Small_Weights.DEFAULT if pretrained else None
        model = models.mobilenet_v3_small(weights=weights)
        classifier_index = 3
    elif backbone == "efficientnet_v2_s":
        weights = models.EfficientNet_V2_S_Weights.DEFAULT if pretrained else None
        model = models.efficientnet_v2_s(weights=weights)
        classifier_index = 1
    else:
        raise ValueError(f"unsupported backbone: {backbone}")
    for parameter in model.features.parameters():
        parameter.requires_grad = False
    model.classifier[classifier_index] = nn.Linear(
        model.classifier[classifier_index].in_features, label_count
    )
    return model, weights


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--initial-checkpoint", type=Path)
    args = parser.parse_args()

    np, torch, nn, optim, DataLoader, WeightedRandomSampler, datasets, models, transforms = _load_dependencies()
    config = _config(args.config)
    random.seed(config["seed"])
    np.random.seed(config["seed"])
    torch.manual_seed(config["seed"])
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(config["seed"])
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    image_size = int(config["input_size"])
    train_augmentation = [
            transforms.RandomResizedCrop(image_size, scale=(0.6, 1.0)),
            transforms.RandomHorizontalFlip(),
    ]
    if config.get("field_augmentation", False):
        train_augmentation.extend([
            transforms.RandomVerticalFlip(p=0.1),
            transforms.RandomRotation(20),
            transforms.ColorJitter(brightness=0.25, contrast=0.25, saturation=0.2, hue=0.04),
            transforms.RandomPerspective(distortion_scale=0.2, p=0.25),
        ])
    train_augmentation.extend([
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    transforms_by_split = {
        "train": transforms.Compose(train_augmentation),
        "val": transforms.Compose([
            transforms.Resize(256),
            transforms.CenterCrop(image_size),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]),
    }
    datasets_by_split = {
        split: datasets.ImageFolder(
            args.data_dir / split,
            transforms_by_split[split],
            allow_empty=True,
        )
        for split in transforms_by_split
    }
    expected_labels = config["labels"]
    if datasets_by_split["train"].classes != expected_labels:
        raise ValueError(
            "Folder class order must match config labels exactly: "
            f"{datasets_by_split['train'].classes} != {expected_labels}"
        )
    worker_count = int(config.get("num_workers", 2))
    field_weight = float(config.get("field_sample_weight", 1.0))
    ood_weight = float(config.get("ood_sample_weight", field_weight))
    sample_weights = [
        ood_weight if Path(path).name.startswith("ood_") else (
            field_weight if Path(path).name.startswith("field_") else 1.0
        )
        for path, _ in datasets_by_split["train"].samples
    ]
    sampler = WeightedRandomSampler(sample_weights, len(sample_weights), replacement=True) if any(weight != 1 for weight in sample_weights) else None
    loaders = {}
    for split, dataset in datasets_by_split.items():
        loaders[split] = DataLoader(
            dataset,
            batch_size=int(config["batch_size"]),
            shuffle=split == "train" and sampler is None,
            sampler=sampler if split == "train" else None,
            num_workers=worker_count,
            persistent_workers=worker_count > 0,
            pin_memory=torch.cuda.is_available(),
        )
    model, _ = _model(
        models, nn, len(expected_labels), backbone=config["backbone"],
        pretrained=args.initial_checkpoint is None,
    )
    if args.initial_checkpoint is not None:
        initial = torch.load(args.initial_checkpoint, map_location="cpu", weights_only=True)
        if initial["labels"] != expected_labels:
            raise ValueError("initial checkpoint label order does not match the new config")
        model.load_state_dict(initial["state_dict"])
    model.to(device)
    target_tensor = torch.tensor(datasets_by_split["train"].targets, dtype=torch.long)
    class_counts = torch.bincount(target_tensor, minlength=len(expected_labels)).float()
    class_weights = len(target_tensor) / (len(expected_labels) * class_counts.clamp_min(1))
    criterion = nn.CrossEntropyLoss(
        weight=class_weights.to(device),
        label_smoothing=float(config.get("label_smoothing", 0.0)),
    )
    feature_blocks = int(config.get("unfreeze_feature_blocks", 0))
    tail_parameters = list(model.features[-feature_blocks:].parameters()) if feature_blocks else []
    optimizer = optim.AdamW(
        [
            {"params": model.classifier.parameters(), "lr": float(config["learning_rate"])},
            {"params": tail_parameters, "lr": float(config.get("backbone_learning_rate", config["learning_rate"]))},
        ],
        weight_decay=float(config.get("weight_decay", 0.0)),
    )
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=int(config["num_epochs"]))
    amp_enabled = device.type == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=amp_enabled)
    best_accuracy = -1.0
    best_epoch = 0
    epochs_without_improvement = 0
    head_only_epochs = int(config.get("head_only_epochs", 0))
    patience = int(config.get("early_stopping_patience", config["num_epochs"]))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(json.dumps({
        "device": str(device), "amp": amp_enabled,
        "class_weights": class_weights.tolist(), "field_sample_weight": field_weight,
        "ood_sample_weight": ood_weight, "backbone": config["backbone"],
        "initial_checkpoint": str(args.initial_checkpoint) if args.initial_checkpoint else None,
    }))

    for epoch in range(int(config["num_epochs"])):
        if epoch == head_only_epochs and tail_parameters:
            for parameter in tail_parameters:
                parameter.requires_grad = True
        metrics: dict[str, float] = {}
        for split in ("train", "val"):
            model.train(split == "train")
            # Keep frozen and fine-tuned batch-normalization statistics stable for small batches.
            model.features.eval()
            correct = total = 0
            accumulated_loss = 0.0
            correct_by_class = [0] * len(expected_labels)
            total_by_class = [0] * len(expected_labels)
            for images, labels in loaders[split]:
                images = images.to(device, non_blocking=amp_enabled)
                labels = labels.to(device, non_blocking=amp_enabled)
                optimizer.zero_grad(set_to_none=True)
                with torch.set_grad_enabled(split == "train"):
                    with torch.amp.autocast(device_type=device.type, enabled=amp_enabled):
                        logits = model(images)
                        loss = criterion(logits, labels)
                if split == "train":
                    scaler.scale(loss).backward()
                    scaler.step(optimizer)
                    scaler.update()
                correct += int((logits.argmax(dim=1) == labels).sum().item())
                predicted = logits.argmax(dim=1)
                for label_index in range(len(expected_labels)):
                    mask = labels == label_index
                    total_by_class[label_index] += int(mask.sum().item())
                    correct_by_class[label_index] += int((predicted[mask] == label_index).sum().item())
                total += int(labels.size(0))
                accumulated_loss += float(loss.detach().item()) * int(labels.size(0))
            metrics[f"{split}_accuracy"] = correct / max(total, 1)
            metrics[f"{split}_loss"] = accumulated_loss / max(total, 1)
            supported_recalls = [
                correct_by_class[index] / class_total
                for index, class_total in enumerate(total_by_class) if class_total
            ]
            metrics[f"{split}_balanced_accuracy"] = sum(supported_recalls) / max(len(supported_recalls), 1)
        scheduler.step()
        print(json.dumps({"epoch": epoch + 1, "fine_tuning": epoch >= head_only_epochs, **metrics}), flush=True)
        selection_metric = config.get("checkpoint_metric", "val_accuracy")
        if selection_metric not in metrics:
            raise ValueError(f"unknown checkpoint metric: {selection_metric}")
        selection_value = metrics[selection_metric]
        if selection_value > best_accuracy:
            best_accuracy = selection_value
            best_epoch = epoch + 1
            epochs_without_improvement = 0
            torch.save({
                "state_dict": model.state_dict(),
                "labels": expected_labels,
                "config": config,
                "val_accuracy": best_accuracy,
                "best_epoch": best_epoch,
                "checkpoint_metric": selection_metric,
            }, args.output_dir / "best.pt")
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= patience:
                print(json.dumps({
                    "early_stopping": True, "best_epoch": best_epoch,
                    "checkpoint_metric": selection_metric, "best_metric": best_accuracy,
                }), flush=True)
                break


if __name__ == "__main__":
    main()
