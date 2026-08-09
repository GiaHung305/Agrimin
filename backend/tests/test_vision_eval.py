import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eval.run_vision_eval import _is_successful_analysis, plantdoc_test_cases


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
