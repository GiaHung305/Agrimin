import os
import sys
import base64
from io import BytesIO

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.multimodal.image_validation import validate_chat_image_payload
from eval.run_vision_eval import (
    _is_successful_analysis,
    benchmark_batches,
    make_quality_variant,
    merge_case_results,
    plantdoc_benchmark_cases,
    plantdoc_test_cases,
    score_case,
    vision_enabled_for_eval,
)


def test_plantdoc_smoke_cases_are_test_only_and_balanced():
    names = [
        "root/train/Tomato leaf/ignored.jpg",
        "root/test/Tomato leaf/tomato-a.jpg",
        "root/test/Tomato Early blight leaf/tomato-b.jpg",
        "root/test/Apple leaf/apple.jpg",
        "root/test/Corn leaf/corn.jpg",
        "root/test/Grape leaf/grape.jpg",
    ]
    cases = plantdoc_test_cases(
        names,
        {
            "Tomato leaf": "healthy",
            "Tomato Early blight leaf": "early_blight",
        },
        limit=4,
    )
    assert len(cases) == 4
    assert sum(expected == "tomato" for _, expected in cases) == 2
    assert sum(expected == "non_tomato" for _, expected in cases) == 2
    assert all("/test/" in member for member, _ in cases)


def test_plantdoc_scope_offset_selects_disjoint_balanced_cases():
    names = [
        "root/test/Tomato leaf/tomato-a.jpg",
        "root/test/Tomato leaf/tomato-b.jpg",
        "root/test/Apple leaf/apple-a.jpg",
        "root/test/Apple leaf/apple-b.jpg",
        "root/test/Corn leaf/corn-a.jpg",
        "root/test/Corn leaf/corn-b.jpg",
    ]
    label_map = {"Tomato leaf": "healthy"}

    first = plantdoc_test_cases(names, label_map, limit=2)
    second = plantdoc_test_cases(names, label_map, limit=2, scope_offset=1)

    assert len(second) == 2
    assert {expected for _, expected in second} == {"tomato", "non_tomato"}
    assert {member for member, _ in first}.isdisjoint(
        member for member, _ in second
    )


def test_unavailable_provider_is_not_a_successful_analysis():
    assert not _is_successful_analysis(
        {"mode": "validation_only", "error": "unavailable"},
        {},
    )


def test_typed_observation_is_a_successful_analysis():
    assert _is_successful_analysis(
        {"mode": "typed_observations", "error": None},
        {"crop_candidate": "tomato"},
    )


def test_benchmark_selection_is_held_out_and_covers_challenge_groups():
    names = [
        "root/test/Tomato leaf/healthy-a.jpg",
        "root/test/Tomato leaf/healthy-b.jpg",
        "root/train/Tomato leaf/train-only.jpg",
        "root/test/Tomato Early blight leaf/early-a.jpg",
        "root/test/Tomato Early blight leaf/early-b.jpg",
        "root/test/Tomato Septoria leaf spot/septoria-a.jpg",
        "root/test/Tomato Septoria leaf spot/septoria-b.jpg",
    ]
    manifest = {
        "plantdoc": {
            "split": "test",
            "healthy": {"classes": ["Tomato leaf"], "samples_per_class": 2},
            "look_alike": {
                "groups": [{
                    "id": "brown_spot_like",
                    "classes": [
                        "Tomato Early blight leaf",
                        "Tomato Septoria leaf spot",
                    ],
                    "samples_per_class": 2,
                }]
            },
        }
    }

    cases = plantdoc_benchmark_cases(names, manifest)

    assert len(cases) == 6
    assert sum(case["category"] == "healthy" for case in cases) == 2
    assert sum(case["category"] == "look_alike" for case in cases) == 4
    assert all("/test/" in case["member"] for case in cases)
    assert {
        case.get("challenge_group")
        for case in cases
        if case["category"] == "look_alike"
    } == {"brown_spot_like"}


def test_benchmark_selection_can_skip_quality_ineligible_members():
    names = [
        "root/test/Tomato leaf/too-small.jpg",
        "root/test/Tomato leaf/usable-a.jpg",
        "root/test/Tomato leaf/usable-b.jpg",
    ]
    manifest = {
        "plantdoc": {
            "split": "test",
            "healthy": {"classes": ["Tomato leaf"], "samples_per_class": 2},
            "look_alike": {"groups": []},
        }
    }

    cases = plantdoc_benchmark_cases(
        names,
        manifest,
        member_is_eligible=lambda member: "too-small" not in member,
    )

    assert {case["member"] for case in cases} == {
        "root/test/Tomato leaf/usable-a.jpg",
        "root/test/Tomato leaf/usable-b.jpg",
    }


def _checkerboard_jpeg() -> bytes:
    image = Image.new("RGB", (512, 512), "white")
    pixels = image.load()
    for y in range(512):
        for x in range(512):
            value = 20 if ((x // 16) + (y // 16)) % 2 else 235
            pixels[x, y] = (value, value, value)
    output = BytesIO()
    image.save(output, format="JPEG", quality=95)
    return output.getvalue()


def test_dark_and_blur_variants_are_rejected_by_deterministic_validator():
    source = _checkerboard_jpeg()
    dark = make_quality_variant(
        source,
        {"id": "dark", "brightness_factor": 0.03},
    )
    blurred = make_quality_variant(
        source,
        {"id": "blur", "gaussian_radius": 24.0},
    )

    dark_result = validate_chat_image_payload(
        base64.b64encode(dark).decode("ascii"), "image/jpeg"
    )
    blur_result = validate_chat_image_payload(
        base64.b64encode(blurred).decode("ascii"), "image/jpeg"
    )

    assert "too_dark" in dark_result.observation["quality_issues"]
    assert "blurry_or_low_detail" in blur_result.observation["quality_issues"]
    assert not dark_result.observation["usable_for_vision"]
    assert not blur_result.observation["usable_for_vision"]


def test_eval_user_allowlist_matches_production_gate():
    assert vision_enabled_for_eval(
        False,
        "GIAHUNG30505@gmail.com",
        "someone@example.com, giahung30505@gmail.com",
    )
    assert not vision_enabled_for_eval(
        False,
        "other@example.com",
        "giahung30505@gmail.com",
    )
    assert vision_enabled_for_eval(True, "", "")


def test_missing_observation_never_passes_healthy_case():
    result = score_case(
        {"case_id": "healthy-1", "category": "healthy"},
        {"trace": {"vision": {
            "mode": "validation_only",
            "error": "unavailable",
            "visual_observations": [],
        }}},
    )

    assert not result["successful_analysis"]
    assert not result["passed"]


def test_ood_requires_typed_out_of_domain_and_graph_rejection():
    result = score_case(
        {"case_id": "ood-rocket", "category": "ood"},
        {"trace": {"vision": {
            "mode": "typed_observations",
            "error": None,
            "stop_reason": "image_irrelevant",
            "observations": [{"quality_issues": []}],
            "visual_observations": [{
                "relevance": "out_of_domain",
                "crop_candidate": None,
                "visible_symptoms": [],
                "confidence": 0.98,
            }],
        }}},
    )

    assert result["successful_analysis"]
    assert result["passed"]


def test_look_alike_scores_observation_not_disease_name():
    result = score_case(
        {"case_id": "lookalike-1", "category": "look_alike"},
        {"trace": {"vision": {
            "mode": "typed_observations",
            "error": None,
            "visual_observations": [{
                "relevance": "agriculture_plant",
                "crop_candidate": "cà chua",
                "visible_symptoms": [{"description": "đốm nâu rải rác"}],
                "confidence": 0.8,
            }],
        }}},
    )

    assert result["passed"]
    assert "diagnosis" not in result


def test_benchmark_batches_never_mix_categories_and_cap_at_two():
    payloads = [
        {"case_id": "healthy-1", "category": "healthy"},
        {"case_id": "healthy-2", "category": "healthy"},
        {"case_id": "look-1", "category": "look_alike"},
        {"case_id": "look-2", "category": "look_alike"},
        {"case_id": "look-3", "category": "look_alike"},
        {"case_id": "ood-1", "category": "ood"},
        {"case_id": "ood-2", "category": "ood"},
    ]

    batches = benchmark_batches(payloads, batch_size=2)

    assert [len(batch) for batch in batches] == [2, 2, 1, 1, 1]
    assert all(len({case["category"] for case in batch}) == 1 for batch in batches)
    assert [
        case["case_id"] for batch in batches for case in batch
    ] == [case["case_id"] for case in payloads]


def test_score_case_selects_its_own_observation_from_a_two_image_batch():
    response = {"trace": {"vision": {
        "mode": "typed_observations",
        "error": None,
        "observations": [
            {"image_id": "first", "quality_issues": []},
            {"image_id": "second", "quality_issues": []},
        ],
        "visual_observations": [
            {
                "image_id": "first",
                "relevance": "agriculture_plant",
                "crop_candidate": "ớt",
                "visible_symptoms": [],
            },
            {
                "image_id": "second",
                "relevance": "agriculture_plant",
                "crop_candidate": "cà chua",
                "visible_symptoms": [],
                "confidence": 0.9,
            },
        ],
    }}}

    result = score_case(
        {"case_id": "healthy-2", "category": "healthy", "image_id": "second"},
        response,
    )

    assert result["crop_candidate"] == "cà chua"
    assert result["passed"]


def test_merge_case_results_replaces_reruns_and_drops_removed_cases():
    merged = merge_case_results(
        ["healthy-1", "ood-1", "new-lookalike"],
        [
            {"case_id": "healthy-1", "passed": True},
            {"case_id": "ood-1", "passed": False},
            {"case_id": "old-low-resolution", "passed": False},
        ],
        [
            {"case_id": "ood-1", "passed": True},
            {"case_id": "new-lookalike", "passed": True},
        ],
    )

    assert merged == [
        {"case_id": "healthy-1", "passed": True},
        {"case_id": "ood-1", "passed": True},
        {"case_id": "new-lookalike", "passed": True},
    ]
