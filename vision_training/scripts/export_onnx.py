"""Export a reviewed PyTorch checkpoint to ONNX for future server inference."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from vision_training.scripts.train import _load_dependencies, _model


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    _, torch, nn, _, _, _, _, models, _ = _load_dependencies()
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    config = checkpoint["config"]
    model, _ = _model(
        models, nn, len(checkpoint["labels"]),
        backbone=config["backbone"], pretrained=False,
    )
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    sample = torch.randn(1, 3, int(config["input_size"]), int(config["input_size"]))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        model,
        (sample,),
        args.output,
        input_names=["image"],
        output_names=["logits"],
        dynamic_shapes=({0: torch.export.Dim("batch")},),
        external_data=False,
        dynamo=True,
        verify=True,
    )
    metadata_path = args.output.with_suffix(".labels.json")
    metadata_path.write_text(json.dumps({
        "model_version": config["model_version"],
        "crop": config["crop"],
        "labels": checkpoint["labels"],
        "input_size": config["input_size"],
        "normalization": {"mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225]},
    }, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
