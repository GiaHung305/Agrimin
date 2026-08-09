import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from vision_training.scripts.clean_imagefolder import clean_manifest
from vision_training.scripts.download_source import download_from_kaggle, load_source, sha256_file
from vision_training.scripts.evaluate import promotion_decision
from vision_training.scripts.evaluate_external_zip import archive_records, balanced_ood_sample
from vision_training.scripts.inventory_images import inventory
from vision_training.scripts.prepare_imagefolder import prepare
from vision_training.scripts.prepare_plantvillage_hf import lookup_leaf_id, validation_leaf_ids
from vision_training.scripts.prepare_field_adaptation import field_validation_members


class SourceToolTests(unittest.TestCase):
    def test_registry_has_provenance_and_explicit_noncommercial_gate(self):
        registry = Path("vision_training/source_registry.json")
        plantwild = load_source(registry, "plantwild_v2")
        self.assertEqual(plantwild["license_status"], "CC-BY-NC-4.0")
        self.assertFalse(plantwild["production_eligible"])

    def test_inventory_removes_exact_duplicate_and_maps_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            label_dir = root / "Ripe"
            label_dir.mkdir()
            (label_dir / "first.jpg").write_bytes(b"same image payload")
            (label_dir / "second.jpg").write_bytes(b"same image payload")
            rows, duplicates = inventory(root, "example", {"Ripe": "ripe"})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["label"], "ripe")
        self.assertEqual(len(duplicates), 1)

    def test_kaggle_download_requires_local_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            source = {"id": "example", "kaggle_dataset": "owner/dataset"}
            with (
                patch("vision_training.scripts.download_source.Path.is_file", return_value=False),
                patch("vision_training.scripts.download_source.shutil.which", return_value=None),
            ):
                with self.assertRaisesRegex(RuntimeError, "Kaggle CLI was not found"):
                    download_from_kaggle(source, Path(directory))

    def test_sha256_file_reads_content_in_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "payload.bin"
            path.write_bytes(b"abc")
            self.assertEqual(
                sha256_file(path),
                "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            )

    def test_prepare_keeps_val_and_prevents_duplicate_split_leakage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            for split in ("train", "val"):
                (root / split / "Ripe").mkdir(parents=True)
            (root / "val" / "Ripe" / "reference.jpg").write_bytes(b"duplicate")
            (root / "train" / "Ripe" / "duplicate.jpg").write_bytes(b"duplicate")
            (root / "train" / "Ripe" / "test.jpg").write_bytes(b"other")
            rows, duplicates = prepare(
                root,
                Path(directory) / "prepared",
                "example",
                {"Ripe": "ripe"},
                test_fraction=0.999999,
            )
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(duplicates), 1)
        self.assertEqual({row["split"] for row in rows}, {"val", "test"})

    def test_clean_manifest_standardizes_and_rejects_canonical_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            image = Image.new("RGB", (80, 100), (40, 120, 80))
            image.save(source / "first.png")
            image.save(source / "second.png")
            manifest = root / "manifest.csv"
            manifest.write_text(
                "image_path,split,label,capture_group,source,consent_status,notes\n"
                f"{source / 'first.png'},train,ripe,one,example,public_license_reviewed,\n"
                f"{source / 'second.png'},test,ripe,two,example,public_license_reviewed,\n",
                encoding="utf-8",
            )
            report = clean_manifest(manifest, root / "clean", max_side=64, min_side=32)
            self.assertEqual(report["kept_images"], 1)
            self.assertEqual(report["rejected_images"], 1)
            output = next((root / "clean" / "train" / "ripe").glob("*.jpg"))
            with Image.open(output) as cleaned:
                self.assertEqual(cleaned.mode, "RGB")
                self.assertEqual(cleaned.size, (51, 64))

    def test_clean_manifest_applies_explicit_reviewed_quality_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "manifest.csv"
            manifest.write_text(
                "image_path,split,label,capture_group,source,consent_status,notes\n"
                "example.jpg,train,damaged,one,example,public_license_reviewed,\n",
                encoding="utf-8",
            )
            with patch(
                "vision_training.scripts.clean_imagefolder.canonicalize",
                return_value=(b"canonical-jpeg", ["low_detail"]),
            ):
                report = clean_manifest(
                    manifest,
                    root / "clean",
                    max_side=64,
                    min_side=32,
                    reject_quality_flags={"low_detail"},
                )
        self.assertEqual(report["kept_images"], 0)
        self.assertEqual(report["rejected_images"], 1)
        self.assertEqual(report["rejected_quality_flags"], ["low_detail"])

    def test_promotion_decision_reports_each_failed_gate(self):
        config = {
            "promotion_min_test_accuracy": 0.9,
            "promotion_min_macro_f1": 0.88,
            "promotion_max_low_confidence_rate": 0.25,
        }
        passed, failures = promotion_decision(config, 0.91, 0.87, 0.3)
        self.assertFalse(passed)
        self.assertEqual(
            failures,
            ["macro_f1_below_threshold", "low_confidence_rate_above_threshold"],
        )

    def test_validation_leaf_ids_keeps_groups_and_each_label_represented(self):
        records = [
            ("leaf-a", "healthy"),
            ("leaf-a", "healthy"),
            ("leaf-b", "healthy"),
            ("leaf-c", "early_blight"),
            ("leaf-d", "early_blight"),
        ]
        selected = validation_leaf_ids(records, fraction=0.5, seed=42)
        self.assertEqual(len(selected.intersection({"leaf-a", "leaf-b"})), 1)
        self.assertEqual(len(selected.intersection({"leaf-c", "leaf-d"})), 1)

    def test_plantvillage_leaf_lookup_matches_class_suggestion(self):
        leaf_map = {
            "com.g_fl 8310": ["Apple___healthy:::1.0", "Tomato___Target_Spot:::243.0"]
        }
        leaf_id = lookup_leaf_id(
            "raw/color/Tomato___Target_Spot/id___Com.G_FL 8310.JPG",
            "Tomato___Target_Spot",
            leaf_map,
        )
        self.assertEqual(leaf_id, "Tomato___Target_Spot:::243.0")

    def test_external_archive_mapping_separates_mapped_and_ood(self):
        names = [
            "root/test/Tomato leaf/image.jpg",
            "root/train/Apple leaf/image.jpg",
            "root/LICENSE.txt",
        ]
        mapped, ood = archive_records(names, {"Tomato leaf": "healthy"})
        self.assertEqual(mapped, [(names[0], "healthy", "Tomato leaf")])
        self.assertEqual(ood, [(names[1], "Apple leaf")])
        self.assertEqual(balanced_ood_sample(ood, 1), ood)

    def test_external_archive_mapping_can_hold_out_test_split(self):
        names = [
            "root/test/Tomato leaf/test.jpg",
            "root/train/Tomato leaf/train.jpg",
            "root/test/Apple leaf/ood.jpg",
        ]
        mapped, ood = archive_records(names, {"Tomato leaf": "healthy"}, {"test"})
        self.assertEqual(mapped, [(names[0], "healthy", "Tomato leaf")])
        self.assertEqual(ood, [(names[2], "Apple leaf")])

    def test_field_validation_is_stratified_and_deterministic(self):
        records = [
            ("a", "healthy", "1"), ("b", "healthy", "2"),
            ("c", "early_blight", "3"), ("d", "early_blight", "4"),
        ]
        first = field_validation_members(records, 0.5, 42)
        second = field_validation_members(records, 0.5, 42)
        self.assertEqual(first, second)
        self.assertEqual(len(first.intersection({"a", "b"})), 1)
        self.assertEqual(len(first.intersection({"c", "d"})), 1)
