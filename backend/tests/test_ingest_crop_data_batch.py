from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from eval import ingest_crop_data_batch as crop_batch
from eval.ingest_crop_data_batch import (
    extract_dnn_voice,
    extract_html_body,
    extract_html_element,
    exclude_marker_ranges,
    fetch_sources,
    load_manifest,
    parse_database_datetime,
    slice_markers,
    validate_content,
)


MANIFEST_PATH = BACKEND_ROOT / "eval" / "crop_data_expansion_batch_1_v1.json"
BATCH_2_PATH = BACKEND_ROOT / "eval" / "crop_data_expansion_batch_2_v1.json"
BATCH_3_PATH = BACKEND_ROOT / "eval" / "crop_data_expansion_batch_3_v1.json"
BATCH_4_PATH = BACKEND_ROOT / "eval" / "crop_data_expansion_batch_4_v1.json"
BATCH_5_PATH = BACKEND_ROOT / "eval" / "crop_data_expansion_batch_5_v1.json"
BATCH_6_PATH = BACKEND_ROOT / "eval" / "crop_data_expansion_batch_6_v1.json"
BATCH_7_PATH = BACKEND_ROOT / "eval" / "crop_data_expansion_batch_7_v1.json"
BATCH_8_PATH = BACKEND_ROOT / "eval" / "crop_data_expansion_batch_8_v1.json"
BATCH_9_PATH = BACKEND_ROOT / "eval" / "crop_data_expansion_batch_9_v1.json"
BATCH_10_PATH = BACKEND_ROOT / "eval" / "crop_data_expansion_batch_10_v1.json"
BATCH_11_PATH = BACKEND_ROOT / "eval" / "crop_data_expansion_batch_11_v1.json"
BATCH_12_PATH = BACKEND_ROOT / "eval" / "crop_data_expansion_batch_12_v1.json"
BATCH_13_PATH = BACKEND_ROOT / "eval" / "crop_data_expansion_batch_13_v1.json"
BATCH_14_PATH = BACKEND_ROOT / "eval" / "crop_data_expansion_batch_14_v1.json"
BATCH_15_PATH = BACKEND_ROOT / "eval" / "crop_data_expansion_batch_15_v1.json"
BATCH_16_PATH = BACKEND_ROOT / "eval" / "crop_data_expansion_batch_16_v1.json"


def test_batch_manifest_covers_eleven_policy_crops() -> None:
    manifest = load_manifest(MANIFEST_PATH)
    crop_keys = {
        crop_key
        for document in manifest["documents"]
        for crop_key in document["crop_keys"]
    }

    assert manifest["version"] == "crop-data-expansion-batch-1-v1"
    assert len(manifest["documents"]) == 10
    assert len(crop_keys) == 13
    assert {
        "bitter_melon",
        "bottle_gourd",
        "chili",
        "cucumber",
        "eggplant",
        "green_bean",
        "mustard_greens",
        "pumpkin",
        "water_spinach",
        "winter_melon",
        "yardlong_bean",
    } <= crop_keys


def test_second_batch_covers_food_crops_and_brassicas() -> None:
    manifest = load_manifest(BATCH_2_PATH)
    crop_keys = {
        crop_key
        for document in manifest["documents"]
        for crop_key in document["crop_keys"]
    }

    assert manifest["version"] == "crop-data-expansion-batch-2-v1"
    assert len(manifest["documents"]) == 6
    assert {
        "maize",
        "potato",
        "bell_pepper",
        "malabar_spinach",
        "broccoli",
        "cauliflower",
        "kohlrabi",
    } <= crop_keys


def test_third_batch_covers_twelve_p0_vegetables() -> None:
    manifest = load_manifest(BATCH_3_PATH)
    crop_keys = {
        crop_key
        for document in manifest["documents"]
        for crop_key in document["crop_keys"]
    }

    assert manifest["version"] == "crop-data-expansion-batch-3-v1"
    assert len(manifest["documents"]) == 17
    assert crop_keys == {
        "amaranth",
        "asparagus",
        "chayote",
        "katuk",
        "melon",
        "okra",
        "onion",
        "pea",
        "radish",
        "spring_onion",
        "sweet_corn",
        "watermelon",
    }


def test_fourth_batch_covers_ten_p0_herbs_without_pesticide_sections() -> None:
    manifest = load_manifest(BATCH_4_PATH)
    crop_keys = {
        crop_key
        for document in manifest["documents"]
        for crop_key in document["crop_keys"]
    }

    assert manifest["version"] == "crop-data-expansion-batch-4-v1"
    assert len(manifest["documents"]) == 10
    assert crop_keys == {
        "basil",
        "coriander",
        "culantro",
        "dill",
        "fish_mint",
        "marjoram",
        "mint",
        "perilla",
        "vietnamese_coriander",
        "wild_betel",
    }
    assert all(
        document["end_marker"] == "* Phòng trừ sâu bệnh"
        for document in manifest["documents"]
    )


def test_fifth_batch_covers_eight_p0_food_crops_with_safe_slices() -> None:
    manifest = load_manifest(BATCH_5_PATH)
    crop_keys = {
        crop_key
        for document in manifest["documents"]
        for crop_key in document["crop_keys"]
    }

    assert manifest["version"] == "crop-data-expansion-batch-5-v1"
    assert len(manifest["documents"]) == 13
    assert crop_keys == {
        "cassava", "garlic", "ginger", "peanut", "pennywort",
        "soybean", "sweet_potato", "turmeric",
    }
    assert {
        "3.2. Chất lượng hom giống",
        "4.5. Phòng trừ cỏ dại",
        "5. Trồng xen và luân canh",
        "Chuẩn bị hom hoặc cây giống",
        "Phòng trừ sâu bệnh",
        "7. Phòng trừ sâu bệnh",
        "4. Phòng chữa bệnh cho tỏi",
    } <= {document.get("end_marker") for document in manifest["documents"]}


def test_sixth_batch_covers_seven_p0_crops_with_safe_slices() -> None:
    manifest = load_manifest(BATCH_6_PATH)
    crop_keys = {
        crop_key
        for document in manifest["documents"]
        for crop_key in document["crop_keys"]
    }

    assert manifest["version"] == "crop-data-expansion-batch-6-v1"
    assert len(manifest["documents"]) == 10
    assert crop_keys == {
        "artichoke",
        "banana",
        "celery",
        "chives",
        "luffa",
        "spinach",
        "taro",
    }
    assert all(document.get("start_marker") for document in manifest["documents"])
    assert all(document.get("end_marker") for document in manifest["documents"])


def test_seventh_batch_covers_seven_p0_crops_with_safe_slices() -> None:
    manifest = load_manifest(BATCH_7_PATH)
    crop_keys = {
        crop_key
        for document in manifest["documents"]
        for crop_key in document["crop_keys"]
    }

    assert manifest["version"] == "crop-data-expansion-batch-7-v1"
    assert len(manifest["documents"]) == 12
    assert crop_keys == {
        "beetroot",
        "chinese_cabbage",
        "chrysanthemum_greens",
        "jicama",
        "jute_mallow",
        "shallot",
        "winged_bean",
    }
    assert all(document["format"] == "html_markers" for document in manifest["documents"])
    assert all(document.get("start_marker") for document in manifest["documents"])
    assert all(document.get("end_marker") for document in manifest["documents"])


def test_eighth_batch_covers_all_sixteen_remaining_p0_crops() -> None:
    manifest = load_manifest(BATCH_8_PATH)
    crop_keys = {
        crop_key
        for document in manifest["documents"]
        for crop_key in document["crop_keys"]
    }

    assert manifest["version"] == "crop-data-expansion-batch-8-v1"
    assert len(manifest["documents"]) == 17
    assert crop_keys == {
        "bok_choy", "brussels_sprouts", "chard", "galangal", "kale",
        "leek", "lemongrass", "lotus_root", "mung_bean", "parsley",
        "purslane", "taro_stem", "turnip", "watercress", "yam", "zucchini",
    }
    assert all(document["format"] == "html_markers" for document in manifest["documents"])
    assert all(document.get("start_marker") for document in manifest["documents"])
    assert all(document.get("end_marker") for document in manifest["documents"])


def test_ninth_batch_deepens_vietnamese_zucchini_and_lemongrass_sources() -> None:
    manifest = load_manifest(BATCH_9_PATH)
    crop_keys = {
        crop_key
        for document in manifest["documents"]
        for crop_key in document["crop_keys"]
    }

    assert manifest["version"] == "crop-data-expansion-batch-9-v1"
    assert len(manifest["documents"]) == 6
    assert crop_keys == {"lemongrass", "zucchini"}
    assert all(document["format"] == "html_markers" for document in manifest["documents"])
    assert all(document.get("published_date") for document in manifest["documents"])
    assert any(document.get("exclude_marker_ranges") for document in manifest["documents"])


def test_tenth_batch_slices_northern_nutrition_by_exact_vegetable() -> None:
    manifest = load_manifest(BATCH_10_PATH)
    crop_keys = {
        crop_key
        for document in manifest["documents"]
        for crop_key in document["crop_keys"]
    }

    assert manifest["version"] == "crop-data-expansion-batch-10-v1"
    assert len(manifest["documents"]) == 6
    assert crop_keys == {
        "cabbage", "cucumber", "malabar_spinach", "radish", "tomato",
        "water_spinach",
    }
    assert len({document["source"] for document in manifest["documents"]}) == 1
    assert all("1 ha" in document["content_prefix"] for document in manifest["documents"])


def test_eleventh_batch_deepens_vietnamese_disease_and_harvest_guidance() -> None:
    manifest = load_manifest(BATCH_11_PATH)
    crop_keys = {
        crop_key
        for document in manifest["documents"]
        for crop_key in document["crop_keys"]
    }

    assert manifest["version"] == "crop-data-expansion-batch-11-v1"
    assert len(manifest["documents"]) == 8
    assert crop_keys == {"banana", "cassava", "potato"}
    assert all(document["format"] == "html_markers" for document in manifest["documents"])
    assert all(document.get("published_date") for document in manifest["documents"])
    assert any(document.get("exclude_marker_ranges") for document in manifest["documents"])
    assert all(
        "thuốc" not in document.get("required_terms", [])
        for document in manifest["documents"]
    )


def test_twelfth_batch_adds_regional_vegetable_harvest_depth() -> None:
    manifest = load_manifest(BATCH_12_PATH)
    crop_keys = {
        crop_key
        for document in manifest["documents"]
        for crop_key in document["crop_keys"]
    }

    assert manifest["version"] == "crop-data-expansion-batch-12-v1"
    assert len(manifest["documents"]) == 5
    assert crop_keys == {"asparagus", "bitter_melon", "carrot", "cucumber", "okra"}
    assert all(document["format"] == "html_markers" for document in manifest["documents"])
    assert sum(bool(document.get("forbidden_terms")) for document in manifest["documents"]) == 3


def test_thirteenth_batch_adds_second_sources_without_importing_pesticide_tables() -> None:
    manifest = load_manifest(BATCH_13_PATH)
    crop_keys = {
        crop_key
        for document in manifest["documents"]
        for crop_key in document["crop_keys"]
    }

    assert manifest["version"] == "crop-data-expansion-batch-13-v1"
    assert len(manifest["documents"]) == 3
    assert len(crop_keys) == 35
    assert {
        "bell_pepper", "broccoli", "cauliflower", "chili", "chives",
        "coriander", "leek", "parsley", "shallot", "spring_onion",
    } <= crop_keys
    assert all(document["format"] == "html_markers" for document in manifest["documents"])
    assert all(document.get("forbidden_terms") for document in manifest["documents"])
    assert all("Florida" in document["content_prefix"] for document in manifest["documents"])


def test_fourteenth_batch_deepens_tropical_vegetables_and_legumes_safely() -> None:
    manifest = load_manifest(BATCH_14_PATH)
    crop_keys = {
        crop_key
        for document in manifest["documents"]
        for crop_key in document["crop_keys"]
    }

    assert manifest["version"] == "crop-data-expansion-batch-14-v1"
    assert len(manifest["documents"]) == 9
    assert crop_keys == {
        "amaranth", "bok_choy", "bottle_gourd", "luffa", "soybean",
        "winged_bean", "yardlong_bean",
    }
    assert all(document["format"] == "html_markers" for document in manifest["documents"])
    assert all(document.get("forbidden_terms") for document in manifest["documents"])


def test_fifteenth_batch_deepens_remaining_specialty_crops_safely() -> None:
    manifest = load_manifest(BATCH_15_PATH)
    crop_keys = {
        crop_key
        for document in manifest["documents"]
        for crop_key in document["crop_keys"]
    }

    assert manifest["version"] == "crop-data-expansion-batch-15-v1"
    assert len(manifest["documents"]) == 16
    assert crop_keys == {
        "artichoke", "chrysanthemum_greens", "culantro", "dragon_fruit",
        "fish_mint", "galangal", "garlic", "jicama", "jute_mallow",
        "mango", "pepper", "perilla", "pineapple", "purslane", "taro",
        "vietnamese_coriander", "watercress",
    }
    assert all(document["format"] == "html_markers" for document in manifest["documents"])
    assert all(document.get("forbidden_terms") for document in manifest["documents"])


def test_sixteenth_batch_closes_the_final_nine_crop_source_gaps() -> None:
    manifest = load_manifest(BATCH_16_PATH)
    crop_keys = {
        crop_key
        for document in manifest["documents"]
        for crop_key in document["crop_keys"]
    }

    assert manifest["version"] == "crop-data-expansion-batch-16-v1"
    assert len(manifest["documents"]) == 11
    assert crop_keys == {
        "katuk", "lotus_root", "mung_bean", "peanut", "pennywort",
        "taro_stem", "wild_betel", "winter_melon", "yam",
    }
    assert sum(document["format"] == "pdf" for document in manifest["documents"]) == 8
    assert all(document.get("forbidden_terms") for document in manifest["documents"])


def test_html_extractor_reads_only_selected_element() -> None:
    content = extract_html_element(
        b'<nav>noise</nav><div id="article"><h1>Rau cai</h1>'
        b'<p>Ky thuat <strong>an toan</strong></p></div><footer>noise</footer>',
        "article",
    )

    assert "Rau cai" in content
    assert "Ky thuat an toan" in content
    assert "noise" not in content


def test_html_extractor_reads_only_selected_class() -> None:
    content = extract_html_element(
        b'<nav>noise</nav><article class="detail art-cont">'
        b'<h1>Ngo ngot</h1><p>Ky thuat canh tac</p></article><footer>noise</footer>',
        element_class="art-cont",
    )

    assert "Ngo ngot" in content
    assert "Ky thuat canh tac" in content
    assert "noise" not in content


def test_dnn_voice_extractor_combines_summary_and_article() -> None:
    content = extract_dnn_voice(
        b'<input id="x_HidSummaryVoice" value="Tom tat cay ngo" />'
        b'<input id="x_HidContentVoice" value="Ky thuat gieo trong &amp; cham soc" />'
    )

    assert content == "Tom tat cay ngo\nKy thuat gieo trong & cham soc"


def test_html_body_extractor_ignores_executable_and_style_content() -> None:
    content = extract_html_body(
        b'<nav>noise</nav><article><h1>Rau cai</h1><script>secret()</script>'
        b'<style>.hidden{}</style><p>Ky thuat <strong>an toan</strong></p></article>'
    )

    assert "Rau cai" in content
    assert "Ky thuat an toan" in content
    assert "secret" not in content
    assert "hidden" not in content


def test_content_validation_rejects_missing_crop_term() -> None:
    entry = {"title": "Test", "min_chars": 500, "required_terms": ["dua leo"]}

    with pytest.raises(ValueError, match="required_terms_missing"):
        validate_content(entry, "noi dung khac " * 100)


def test_content_validation_rejects_forbidden_legacy_term() -> None:
    entry = {
        "title": "Safe IPM slice",
        "min_chars": 10,
        "required_terms": ["luân canh"],
        "forbidden_terms": ["thuốc OLD-1"],
    }

    with pytest.raises(ValueError, match="forbidden_terms_present"):
        validate_content(entry, "Luân canh và dùng thuốc OLD-1")


def test_pdf_section_markers_remove_neighboring_crop_content() -> None:
    content = "tail chili\n7. CÀ TÍM\nnoi dung ca tim\n8. ĐẬU COVE, ĐẬU ĐŨA"

    assert slice_markers(content, "7. CÀ TÍM", "8. ĐẬU COVE, ĐẬU ĐŨA") == (
        "7. CÀ TÍM\nnoi dung ca tim"
    )


def test_exclude_marker_ranges_removes_legacy_chemical_span() -> None:
    content = (
        "IPM canh tac\nNgoai ra, co the dung thuoc OLD-1\n"
        "Benh hai chinh\nBien phap canh tac"
    )

    result = exclude_marker_ranges(
        content,
        [{"start_marker": "Ngoai ra", "end_marker": "Benh hai chinh"}],
    )

    assert result == "IPM canh tac\nBenh hai chinh\nBien phap canh tac"
    assert "OLD-1" not in result


def test_published_timestamp_is_normalized_to_utc_naive_for_database() -> None:
    parsed = parse_database_datetime("2019-09-26T17:27:00+07:00")

    assert parsed.isoformat() == "2019-09-26T10:27:00"
    assert parsed.tzinfo is None


def test_manifest_rejects_non_allowlisted_source(tmp_path: Path) -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["documents"][0]["source"] = "https://example.com/unreviewed.pdf"
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="source_not_allowed"):
        load_manifest(path)


def test_manifest_rejects_invalid_published_date_before_ingest(tmp_path: Path) -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["documents"][0]["published_date"] = "not-an-iso-date"
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="published_date_invalid"):
        load_manifest(path)


@pytest.mark.asyncio
async def test_source_fetch_retries_transient_transport_failure(monkeypatch) -> None:
    class FakeResponse:
        content = b"crop data"

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            self.attempts = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            return None

        async def get(self, url: str):
            self.attempts += 1
            if self.attempts == 1:
                raise httpx.ReadTimeout("temporary", request=httpx.Request("GET", url))
            return FakeResponse()

    async def no_sleep(delay: float) -> None:
        return None

    client = FakeClient()
    monkeypatch.setattr(crop_batch.httpx, "AsyncClient", lambda **kwargs: client)
    monkeypatch.setattr(crop_batch.asyncio, "sleep", no_sleep)

    result = await fetch_sources(
        {"documents": [{"source": "https://example.com/crop"}]}
    )

    assert result == {"https://example.com/crop": b"crop data"}
    assert client.attempts == 2
