import unittest

from vision_training.scripts.validate_dataset import validate_manifest


CONFIG = {
    "model_version": "tomato-v1",
    "labels": ["healthy", "leaf_spot"],
    "min_prototype_images_per_label": 2,
}


def _row(path: str, split: str, label: str, group: str) -> dict[str, str]:
    return {
        "image_path": path,
        "split": split,
        "label": label,
        "capture_group": group,
        "source": "field",
        "consent_status": "verified",
    }


class DatasetValidatorTests(unittest.TestCase):
    def test_manifest_rejects_capture_group_leakage(self):
        rows = [
            _row("a.jpg", "train", "healthy", "farm-a"),
            _row("b.jpg", "val", "leaf_spot", "farm-a"),
            _row("c.jpg", "test", "healthy", "farm-b"),
        ]
        report = validate_manifest(CONFIG, rows, strict_minimum=False)
        self.assertTrue(any("spans splits" in error for error in report.errors))

    def test_manifest_rejects_unverified_consent_and_unknown_label(self):
        row = _row("a.jpg", "train", "unknown", "farm-a")
        row["consent_status"] = "pending"
        report = validate_manifest(CONFIG, [row], strict_minimum=False)
        self.assertTrue(any("not in config" in error for error in report.errors))
        self.assertTrue(any("consent_status" in error for error in report.errors))

    def test_minimum_is_warning_until_promotion_gate(self):
        rows = [
            _row("a.jpg", "train", "healthy", "farm-a"),
            _row("b.jpg", "val", "leaf_spot", "farm-b"),
            _row("c.jpg", "test", "healthy", "farm-c"),
        ]
        report = validate_manifest(CONFIG, rows, strict_minimum=False)
        self.assertFalse(report.errors)
        self.assertTrue(report.warnings)
        strict_report = validate_manifest(CONFIG, rows, strict_minimum=True)
        self.assertTrue(strict_report.errors)

    def test_public_license_reviewed_status_is_allowed(self):
        rows = [
            _row("a.jpg", "train", "healthy", "farm-a"),
            _row("b.jpg", "val", "leaf_spot", "farm-b"),
            _row("c.jpg", "test", "healthy", "farm-c"),
        ]
        rows[0]["consent_status"] = "public_license_reviewed"
        report = validate_manifest(CONFIG, rows, strict_minimum=False)
        self.assertFalse(report.errors)
