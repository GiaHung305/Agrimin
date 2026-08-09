# Tomato vision training v1

This workspace trains an offline image classifier for visual observations only.
It is not loaded by FastAPI, does not call paid providers, and does not enable
`VISION_ANALYSIS_ENABLED`.

Two public-data tracks are configured independently:

- `tomato_leaf_disease_v1.json`: PlantVillage tomato baseline; do not treat its
  controlled images as field accuracy.
- `tomato_fruit_quality_v1.json`: ripe, unripe, old and damaged tomato fruit.

Review `source_registry.json` before any download. `PlantWild v2` is explicitly
internal non-commercial evaluation only and is not an automated download target.

## Label policy

`healthy`, `yellowing`, `leaf_spot`, and `chewing_damage` describe visible
patterns. `uncertain_or_not_crop` is mandatory for unsuitable images. Do not
use this classifier as a disease diagnosis or treatment recommendation.

## Collect and validate data

Keep original images outside Git under `data/raw/`. Record each image in a CSV
matching `data/manifest_template.csv`. A `capture_group` identifies the same
farm/capture session and must not cross train, validation, and test splits.

```powershell
python -m vision_training.scripts.validate_dataset `
  --config vision_training/configs/tomato_v1.json `
  --manifest vision_training/data/tomato_v1_manifest.csv
```

Use `--strict-minimum` only for promotion review. The default configuration
targets 200 verified images per label before a prototype is considered.

## Download approved public data

Only archives and generated artifacts go under ignored directories. Downloading
requires an explicit flag and writes a SHA-256 provenance record:

```powershell
python -m vision_training.scripts.download_source `
  --registry vision_training/source_registry.json `
  --source enalis_tomatoes `
  --output-dir vision_training/data/raw/archives `
  --allow-download
```

After extracting an archive, inventory it before assigning train/val/test. The
tool skips exact image duplicates, but it cannot infer capture sessions from
public data; do not claim field-level generalization without independent images.

For the approved Enalis fruit-quality dataset, prepare an ImageFolder layout and
reserve a deterministic 10% of its source training split for a held-out test:

```powershell
python -m vision_training.scripts.prepare_imagefolder `
  --source-root vision_training/data/raw/enalis_tomatoes/content/ieee-mbl-cls `
  --output-dir vision_training/data/processed/tomato_fruit_quality_v1 `
  --source-id enalis_tomatoes `
  --label-map vision_training/label_maps/enalis_tomatoes.json
```

The command preserves the source `val` split, removes exact duplicate files
before linking/copying them, and writes `manifest.csv` beside the processed
images. Validate that manifest before training.

For the PlantVillage disease baseline, use the official Hugging Face archive at
the pinned revision. The preparer keeps the official test split, creates
validation groups only from official train leaves, and uses `leaf_id` as the
manifest capture group so images of one physical leaf cannot leak across splits:

```powershell
python -m vision_training.scripts.prepare_plantvillage_hf `
  --output-dir vision_training/data/processed/tomato_leaf_disease_v1 `
  --label-map vision_training/label_maps/plantvillage_tomato.json

python -m vision_training.scripts.validate_dataset `
  --config vision_training/configs/tomato_leaf_disease_v1.json `
  --manifest vision_training/data/processed/tomato_leaf_disease_v1/manifest.csv `
  --strict-minimum
```

PlantVillage is licensed CC-BY-SA-3.0 and uses controlled backgrounds. Treat it
as a research benchmark; review attribution/share-alike obligations and pass an
independent field-image/OOD evaluation before production activation.

Clean the prepared images into a separate canonical dataset before training. It
decodes every file, fixes EXIF orientation, converts to RGB JPEG, caps the long
edge at 1024 px, and removes canonical duplicates. It records unusually dark,
bright, or low-detail images for review but does not silently discard them.

```powershell
python -m vision_training.scripts.clean_imagefolder `
  --manifest vision_training/data/processed/tomato_fruit_quality_v1/manifest.csv `
  --output-dir vision_training/data/processed/tomato_fruit_quality_v1_clean_v2 `
  --reject-quality-flag low_detail

python -m vision_training.scripts.validate_dataset `
  --config vision_training/configs/tomato_fruit_quality_v1.json `
  --manifest vision_training/data/processed/tomato_fruit_quality_v1_clean_v2/manifest.csv `
  --strict-minimum
```

## Train, evaluate, export

Arrange reviewed images outside Git as follows:

```text
data/processed/tomato_fruit_quality_v1_clean_v2/
  train/<label>/
  val/<label>/
  test/<label>/
```

Install `requirements.txt` in Colab, Kaggle, or a dedicated local environment;
do not add PyTorch to the production backend image. Then run:

For the tested Windows CUDA 12.6 environment, install PyTorch from the official
CUDA wheel index before installing the remaining pinned requirements:

```powershell
python -m pip install torch==2.13.0 torchvision==0.28.0 `
  --index-url https://download.pytorch.org/whl/cu126
python -m pip install -r vision_training/requirements.txt
```

Then run:

```powershell
python -m vision_training.scripts.train `
  --config vision_training/configs/tomato_fruit_quality_v1.json `
  --data-dir vision_training/data/processed/tomato_fruit_quality_v1_clean_v2 `
  --output-dir vision_training/artifacts/tomato_fruit_quality_v1

python -m vision_training.scripts.evaluate `
  --checkpoint vision_training/artifacts/tomato_fruit_quality_v1/best.pt `
  --data-dir vision_training/data/processed/tomato_fruit_quality_v1_clean_v2 `
  --output vision_training/artifacts/tomato_fruit_quality_v1/test_report.json

python -m vision_training.scripts.export_onnx `
  --checkpoint vision_training/artifacts/tomato_fruit_quality_v1/best.pt `
  --output vision_training/artifacts/tomato_fruit_quality_v1/model.onnx
```

Passing this source-dataset benchmark does not authorize production activation.
Before any adapter is enabled, add independent real-world fruit images, poor
lighting/background shifts, look-alike produce, and out-of-domain images. Require
safe abstention on low confidence and keep all RAG citation guardrails active.

The disease model uses the same train/evaluate/export commands with
`tomato_leaf_disease_v1.json`, `data/processed/tomato_leaf_disease_v1`, and
`artifacts/tomato_leaf_disease_v1`. Keep it separate from the fruit-quality
model; routing between fruit and leaf observations belongs in the future
vision adapter, behind the default-off feature flag.

Evaluate the frozen disease checkpoint against the pinned PlantDoc field ZIP.
The source `test` split remains held out; a balanced sample of
non-tomato classes measures whether confidence-based OOD rejection is safe:

```powershell
python -m vision_training.scripts.evaluate_external_zip `
  --checkpoint vision_training/artifacts/tomato_leaf_disease_v1/best.pt `
  --archive vision_training/data/raw/archives/plantdoc_field_eval.zip `
  --label-map vision_training/label_maps/plantdoc_tomato_eval.json `
  --output vision_training/artifacts/tomato_leaf_disease_v1/plantdoc_external_report.json
```

If the controlled-domain baseline fails that benchmark, build a domain-adaptation
challenger from PlantVillage train plus PlantDoc train. The second command keeps
PlantDoc test out of the prepared dataset and selects checkpoints on a stratified
PlantDoc-train validation slice:

```powershell
python -m vision_training.scripts.prepare_field_adaptation `
  --base-dir vision_training/data/processed/tomato_leaf_disease_v1 `
  --archive vision_training/data/raw/archives/plantdoc_field_eval.zip `
  --label-map vision_training/label_maps/plantdoc_tomato_eval.json `
  --output-dir vision_training/data/processed/tomato_leaf_disease_field_v3 `
  --field-validation-only

python -m vision_training.scripts.train `
  --config vision_training/configs/tomato_leaf_disease_field_v3.json `
  --data-dir vision_training/data/processed/tomato_leaf_disease_field_v3 `
  --output-dir vision_training/artifacts/tomato_leaf_disease_field_v3 `
  --initial-checkpoint vision_training/artifacts/tomato_leaf_disease_field_v2/best.pt
```

Never use PlantDoc test for training, hyperparameter selection, or threshold
tuning. A better challenger still remains disabled unless both field and OOD
gates pass.
