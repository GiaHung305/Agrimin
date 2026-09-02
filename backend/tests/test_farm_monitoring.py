import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi import HTTPException

from app.api.routes import assistant
from app.persistence.models import (
    FarmMonitoringSchedule,
    FarmRecommendation,
    FarmRiskPrediction,
    FarmTask,
    FarmWeatherObservation,
    Notification,
    NotificationDelivery,
    NotificationDeliveryAttempt,
    PendingAction,
)
from app.services.farm_monitoring import (
    POLICY_VERSION,
    SUPPORTED_VEGETABLE_POLICY_KEYS,
    VEGETABLE_POLICY_SPECS,
    assess_weather_risk,
    assess_tomato_weather_risk,
    build_recommendation_body,
    highest_risk_assessment,
    is_supported_crop,
    is_supported_region,
    recommendation_dedupe_key,
    resolve_growth_stage,
    resolve_monitoring_policy,
    schedule_run_key,
)
from app.tools.weather_tool import summarize_forecast
from app.services.vietnam_regions import (
    LEGACY_PROVINCE_ALIASES,
    LEGACY_WEATHER_GEOCODE_QUERIES,
    VIETNAM_PROVINCE_GEOCODE_QUERIES,
    is_weather_location_reply,
    province_geocode_fallback,
    weather_locations_from_question,
)
from app.workers import assistant_worker as worker


class ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class ScalarsResult:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return self

    def all(self):
        return self.values


def test_tomato_policy_is_bounded_and_uses_dynamic_confidence():
    complete = assess_tomato_weather_risk(
        {
            "date": "2026-08-13",
            "rain_probability": 0.9,
            "humidity": 92,
            "temp": 24,
            "description": "mưa",
        }
    )
    partial = assess_tomato_weather_risk(
        {"date": "2026-08-13", "rain_probability": 0.9}
    )

    assert complete.risk_level == "high"
    assert complete.confidence > partial.confidence
    assert complete.confidence <= 1
    assert POLICY_VERSION == "tomato-moisture-risk-v1"


def test_policy_selects_highest_forecast_risk_and_stable_keys():
    assessment = highest_risk_assessment(
        [
            {"date": "2026-08-13", "rain_probability": 0.1, "humidity": 60},
            {"date": "2026-08-14", "rain_probability": 0.6, "humidity": 90},
        ]
    )
    scheduled_for = datetime(2026, 8, 12, 8, 30, 59)

    assert assessment.risk_level == "high"
    assert schedule_run_key("schedule-1", scheduled_for) == (
        "farm-monitor:schedule-1:2026-08-12T08:30"
    )
    assert recommendation_dedupe_key("schedule-1", assessment.forecast_date) == (
        "farm-risk:schedule-1:2026-08-14:tomato-moisture-risk-v1"
    )


def test_monitoring_scope_accepts_all_named_crops_and_regions():
    assert is_supported_crop("Cà chua")
    assert is_supported_crop("tomato")
    assert is_supported_crop("lúa")
    assert is_supported_crop("măng cụt")
    assert not is_supported_crop("  ")
    assert is_supported_region("Lâm Đồng")
    assert is_supported_region("Lam Dong")
    assert is_supported_region("Đắk Lắk")
    assert is_supported_region("Thành phố Hồ Chí Minh")
    assert is_supported_region("Ho Chi Minh City")
    assert is_supported_region("Bình Thuận")
    assert not is_supported_region("Tokyo")
    assert not is_supported_region(None)
    assert len(VIETNAM_PROVINCE_GEOCODE_QUERIES) == 34
    assert province_geocode_fallback("Tỉnh Đắk Lắk") == "Buon Ma Thuot"
    assert province_geocode_fallback("TP.HCM") == "Ho Chi Minh City"
    assert province_geocode_fallback("Bình Thuận") == "Phan Thiet"
    assert set(LEGACY_WEATHER_GEOCODE_QUERIES) == set(LEGACY_PROVINCE_ALIASES)


@pytest.mark.parametrize(
    "legacy_location,expected_query",
    [
        ("Bình Thuận", "Phan Thiet"),
        ("Ninh Thuận", "Phan Rang-Thap Cham"),
        ("Phú Yên", "Tuy Hoa"),
        ("Đắk Nông", "Gia Nghia"),
        ("Bình Dương", "Thu Dau Mot"),
        ("Quảng Nam", "Tam Ky"),
        ("Sóc Trăng", "Soc Trang"),
    ],
)
def test_legacy_weather_locations_keep_their_local_representative_city(
    legacy_location, expected_query
):
    assert weather_locations_from_question(legacy_location) == [expected_query]


@pytest.mark.parametrize("question,expected", [
    ("Thời tiết ở Đà Lạt hôm nay thế nào?", ["Da Lat"]),
    ("Dong Nai ngay mai co mua khong?", ["Bien Hoa"]),
    ("Dự báo TP.HCM", ["Ho Chi Minh City"]),
    ("Vĩnh Long có mưa không?", ["Vinh Long"]),
    ("Thời tiết Hà Nội và Đà Nẵng", ["Hanoi", "Da Nang"]),
])
def test_weather_location_extraction_supports_city_and_province_aliases(
    question, expected
):
    assert weather_locations_from_question(question) == expected


def test_weather_location_extraction_does_not_infer_unmentioned_place():
    assert weather_locations_from_question("Thời tiết hôm nay thế nào?") == []


@pytest.mark.parametrize(
    "reply",
    [
        "Đà Lạt",
        "Ở Đà Lạt nhé",
        "Mình đang ở tỉnh Lâm Đồng",
        "TP.HCM",
        "Đà Lạt ngày mai",
        "Hà Nội trước",
    ],
)
def test_weather_location_reply_accepts_location_only_answers(reply):
    assert is_weather_location_reply(reply)


@pytest.mark.parametrize(
    "reply",
    [
        "Tôi trồng cà phê ở Đà Lạt",
        "Đà Lạt và Hà Nội",
        "Thời tiết ở Đà Lạt",
        "Tôi cần tưới cây ở Lâm Đồng",
    ],
)
def test_weather_location_reply_rejects_new_or_ambiguous_intents(reply):
    assert not is_weather_location_reply(reply)


def test_policy_registry_handles_specific_and_generic_crops():
    rice = resolve_monitoring_policy("Lúa")
    coffee = resolve_monitoring_policy("cà phê")
    generic = resolve_monitoring_policy("măng cụt")

    assert rice.key == "rice"
    assert coffee.key == "coffee"
    assert generic.key == "generic"
    assert generic.crop_label == "măng cụt"
    assert all(policy.sources for policy in (rice, coffee, generic))

    flood_watch = assess_weather_risk(
        rice,
        {
            "date": "2026-08-13",
            "rain_probability": 0.7,
            "rain_mm": 52,
            "humidity_max": 90,
            "temp_max": 31,
        },
    )
    heat_watch = assess_weather_risk(
        coffee,
        {
            "date": "2026-08-13",
            "rain_probability": 0.1,
            "rain_mm": 0,
            "humidity_max": 55,
            "temp_max": 39,
        },
    )
    assert flood_watch.risk_level == "high"
    assert "daily_rain_at_least_50_mm" in flood_watch.reasons
    assert heat_watch.risk_level == "high"
    assert "maximum_temperature_at_least_38_c" in heat_watch.reasons


@pytest.mark.parametrize(
    ("raw_stage", "expected_key"),
    [
        ("Mới trồng", "initial"),
        ("đẻ nhánh", "development"),
        ("Ra hoa", "mid_season"),
        ("grain filling", "late_season"),
        ("Giữa vụ / sinh sản", "mid_season"),
        ("đang theo dõi", "unspecified"),
        (None, "unspecified"),
    ],
)
def test_growth_stage_aliases_are_normalized_with_safe_fallback(
    raw_stage, expected_key
):
    assert resolve_growth_stage(raw_stage).key == expected_key


def test_known_growth_stage_versions_policy_and_field_action():
    flowering_rice = resolve_monitoring_policy("Lúa", "Ra hoa")
    unknown_rice = resolve_monitoring_policy("Lúa", "không rõ")
    assessment = assess_weather_risk(
        flowering_rice,
        {
            "date": "2026-08-13",
            "rain_probability": 0.9,
            "humidity": 92,
            "temp": 24,
        },
    )
    body = build_recommendation_body(
        province="Lâm Đồng",
        assessment=assessment,
        policy=flowering_rice,
    )

    assert flowering_rice.version == "rice-stage-mid_season-v1"
    assert flowering_rice.reminder_type == "rice_mid_season_weather_watch"
    assert flowering_rice.growth_stage_known is True
    assert assessment.inputs["growth_stage_key"] == "mid_season"
    assert "mực nước ổn định" in body
    assert "Giai đoạn đã ghi nhận" in body
    assert unknown_rice.version == "rice-weather-watch-v1"
    assert unknown_rice.growth_stage_known is False


def test_vegetable_registry_has_broad_bilingual_coverage():
    expected = {
        "cải xanh": ("mustard_greens", "leafy_vegetable"),
        "bông cải xanh": ("broccoli", "brassica_vegetable"),
        "dưa leo": ("cucumber", "cucurbit_vegetable"),
        "cà tím": ("eggplant", "fruiting_vegetable"),
        "đậu đũa": ("yardlong_bean", "legume_vegetable"),
        "cà rốt": ("carrot", "root_vegetable"),
        "khoai tây": ("potato", "tuber_vegetable"),
        "hành tây": ("onion", "allium_vegetable"),
        "rau mùi": ("coriander", "herb_vegetable"),
        "gừng": ("ginger", "rhizome_vegetable"),
        "măng tây": ("asparagus", "stem_flower_vegetable"),
    }

    assert len(VEGETABLE_POLICY_SPECS) >= 75
    assert len(SUPPORTED_VEGETABLE_POLICY_KEYS) >= 80
    for crop, (key, category) in expected.items():
        policy = resolve_monitoring_policy(crop)
        assert policy.key == key
        assert policy.mode == category
        assert policy.version == f"{key}-weather-watch-v1"
        assert len(policy.sources) >= 4


def test_pineapple_policy_is_available_for_audited_corpus_source():
    for crop in ("dứa", "khóm", "thơm", "pineapple"):
        policy = resolve_monitoring_policy(crop)
        assert policy.key == "pineapple"
        assert policy.crop_label == "dứa"


def test_stage_policy_identifiers_fit_persisted_column_limits():
    stage_labels = (
        "Khởi đầu / cây con",
        "Sinh trưởng",
        "Giữa vụ / sinh sản",
        "Cuối vụ / chín",
    )
    crop_labels = [label for label, _, _ in VEGETABLE_POLICY_SPECS.values()]
    for crop in crop_labels:
        for stage in stage_labels:
            policy = resolve_monitoring_policy(crop, stage)
            assert len(policy.version) <= 50
            assert len(policy.reminder_type) <= 50


def test_vegetable_aliases_are_unique_and_english_aliases_resolve():
    owners: dict[str, str] = {}
    for key, (_, _, aliases) in VEGETABLE_POLICY_SPECS.items():
        for alias in aliases:
            assert alias not in owners, f"duplicate alias {alias}"
            owners[alias] = key

    assert resolve_monitoring_policy("bok choy").key == "bok_choy"
    assert resolve_monitoring_policy("bitter gourd").key == "bitter_melon"
    assert resolve_monitoring_policy("yardlong bean").key == "yardlong_bean"
    assert resolve_monitoring_policy("scallion").key == "spring_onion"


def test_vegetable_group_changes_weather_watch_and_safe_field_action():
    leafy = resolve_monitoring_policy("xà lách")
    root = resolve_monitoring_policy("cà rốt")
    hot_day = {
        "date": "2026-08-13",
        "rain_probability": 0.1,
        "rain_mm": 0,
        "humidity_max": 55,
        "temp_max": 39,
    }
    wet_day = {
        "date": "2026-08-13",
        "rain_probability": 0.6,
        "rain_mm": 10,
        "humidity_max": 90,
        "temp_max": 28,
    }

    leafy_watch = assess_weather_risk(leafy, hot_day)
    root_watch = assess_weather_risk(root, wet_day)
    body = build_recommendation_body(
        province="Lâm Đồng", assessment=root_watch, policy=root
    )

    assert leafy_watch.risk_level == "high"
    assert root_watch.risk_level == "high"
    assert leafy_watch.inputs["policy_category"] == "leafy_vegetable"
    assert "vùng rễ/củ" in body
    assert "không phải chẩn đoán bệnh" in body


def test_weather_forecast_aggregates_all_three_hour_intervals():
    entries = [
        {
            "dt_txt": "2026-08-13 00:00:00",
            "main": {"temp": 25, "temp_min": 24, "temp_max": 26, "humidity": 70},
            "weather": [{"description": "ít mây"}],
            "pop": 0.1,
        },
        {
            "dt_txt": "2026-08-13 03:00:00",
            "main": {"temp": 29, "temp_min": 28, "temp_max": 31, "humidity": 91},
            "weather": [{"description": "mưa to"}],
            "pop": 0.9,
            "rain": {"3h": 18.5},
        },
    ]

    day = summarize_forecast(entries)[0]

    assert day["temp"] == 27
    assert day["temp_min"] == 24
    assert day["temp_max"] == 31
    assert day["humidity_max"] == 91
    assert day["rain_probability"] == 0.9
    assert day["rain_mm"] == 18.5
    assert day["description"] == "mưa to"


def test_weather_forecast_groups_unix_timestamps_by_vietnam_date():
    entries = [
        {
            # 2026-08-12 18:00 UTC = 2026-08-13 01:00 in Vietnam.
            "dt": int(datetime(2026, 8, 12, 18, tzinfo=timezone.utc).timestamp()),
            "dt_txt": "2026-08-12 18:00:00",
            "main": {"temp": 25, "humidity": 75},
            "weather": [{"description": "ít mây"}],
            "pop": 0.1,
        },
        {
            # 2026-08-13 18:00 UTC = 2026-08-14 01:00 in Vietnam.
            "dt": int(datetime(2026, 8, 13, 18, tzinfo=timezone.utc).timestamp()),
            "dt_txt": "2026-08-13 18:00:00",
            "main": {"temp": 26, "humidity": 80},
            "weather": [{"description": "mưa nhẹ"}],
            "pop": 0.4,
        },
    ]

    summary = summarize_forecast(entries)

    assert [day["date"] for day in summary] == ["2026-08-13", "2026-08-14"]


@pytest.mark.asyncio
async def test_create_schedule_requires_explicit_consent():
    db = SimpleNamespace(execute=AsyncMock())

    with pytest.raises(HTTPException, match="consent") as error:
        await assistant.create_monitoring_schedule(
            assistant.MonitoringScheduleCreateRequest(
                consent=False, crop_season_id="season-a"
            ),
            db=db,
            current_user={"id": "user-a"},
        )

    assert error.value.status_code == 422
    db.execute.assert_not_awaited()


def test_farm_profile_payload_does_not_duplicate_crop_from_seasons():
    profile = SimpleNamespace(
        id=uuid.uuid4(),
        name="Nông trại của tôi",
        province="Lâm Đồng",
        area_ha=1.0,
        farming_style="Normal",
    )

    payload = assistant._profile_payload(profile)

    assert "crop" not in payload
    assert payload["province"] == "Lâm Đồng"


@pytest.mark.asyncio
async def test_create_schedule_copies_owned_farm_context():
    profile = SimpleNamespace(
        id=uuid.uuid4(), province="Lâm Đồng", crop="Cà chua"
    )
    plot = SimpleNamespace(
        id=uuid.uuid4(), farm_profile_id=profile.id, status="active"
    )
    season = SimpleNamespace(
        id=uuid.uuid4(),
        plot_id=plot.id,
        crop="Cà chua",
        growth_stage="Mới trồng",
        status="active",
    )
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                ScalarResult(profile),
                ScalarResult(season),
                ScalarResult(plot),
                ScalarResult(None),
            ]
        ),
        add=Mock(),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )

    await assistant.create_monitoring_schedule(
        assistant.MonitoringScheduleCreateRequest(
            consent=True,
            crop_season_id=str(season.id),
            frequency_hours=12,
            notification_scope="push_and_in_app",
        ),
        db=db,
        current_user={"id": "user-a"},
    )

    schedule = db.add.call_args.args[0]
    assert isinstance(schedule, FarmMonitoringSchedule)
    assert schedule.user_id == "user-a"
    assert schedule.farm_profile_id == profile.id
    assert schedule.plot_id == plot.id
    assert schedule.crop_season_id == season.id
    assert schedule.crop == "Cà chua"
    assert schedule.reminder_type == "tomato_initial_weather_watch"
    assert schedule.province == "Lâm Đồng"
    assert schedule.frequency_hours == 12
    assert schedule.consent_granted_at is not None
    statements = [str(call.args[0]) for call in db.execute.await_args_list]
    assert any("crop_seasons.user_id" in statement for statement in statements)
    assert any("farm_plots.user_id" in statement for statement in statements)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_schedule_query_is_owner_scoped():
    db = SimpleNamespace(execute=AsyncMock(return_value=ScalarResult(None)))

    with pytest.raises(HTTPException) as error:
        await assistant.update_monitoring_schedule(
            "schedule-b",
            assistant.MonitoringScheduleUpdateRequest(status="paused"),
            db=db,
            current_user={"id": "user-a"},
        )

    statement = str(db.execute.await_args.args[0])
    assert error.value.status_code == 404
    assert "farm_monitoring_schedules.user_id" in statement


def _schedule_record():
    return SimpleNamespace(
        id=uuid.uuid4(),
        farm_profile_id=uuid.uuid4(),
        plot_id=uuid.uuid4(),
        crop_season_id=uuid.uuid4(),
        crop="tomato",
        province="Lâm Đồng",
        reminder_type="tomato_disease_risk",
        frequency_hours=24,
        notification_scope="in_app",
        status="active",
        consent_granted_at=datetime(2026, 8, 12, 8, 0),
        next_run_at=datetime(2026, 8, 13, 8, 0),
        last_run_at=None,
        last_error_code=None,
        updated_at=datetime(2026, 8, 12, 8, 0),
    )


@pytest.mark.asyncio
async def test_owner_can_pause_and_soft_delete_schedule():
    schedule = _schedule_record()
    db = SimpleNamespace(
        execute=AsyncMock(return_value=ScalarResult(schedule)),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )

    await assistant.update_monitoring_schedule(
        str(schedule.id),
        assistant.MonitoringScheduleUpdateRequest(status="paused"),
        db=db,
        current_user={"id": "user-a"},
    )
    assert schedule.status == "paused"
    assert schedule.next_run_at is None

    response = await assistant.delete_monitoring_schedule(
        str(schedule.id),
        db=db,
        current_user={"id": "user-a"},
    )
    assert response == {"status": "deleted"}
    assert schedule.status == "deleted"
    assert schedule.next_run_at is None
    assert db.commit.await_count == 2


@pytest.mark.asyncio
async def test_plot_and_active_season_are_owned_and_explicit():
    profile = SimpleNamespace(id=uuid.uuid4())
    db = SimpleNamespace(
        execute=AsyncMock(return_value=ScalarResult(profile)),
        add=Mock(),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )

    await assistant.create_farm_plot(
        assistant.FarmPlotCreateRequest(
            name="Nhà kính A",
            area_ha=0.4,
            location_note="Khu phía đông",
            latitude=11.941,
            longitude=108.438,
            elevation_m=1500,
            location_accuracy_m=8,
            location_source="device",
        ),
        db=db,
        current_user={"id": "user-a"},
    )
    plot = db.add.call_args.args[0]
    assert plot.user_id == "user-a"
    assert plot.farm_profile_id == profile.id
    assert plot.status == "active"
    assert plot.latitude == 11.941
    assert plot.longitude == 108.438
    assert plot.location_accuracy_m == 8
    assert plot.coordinates_updated_at is not None

    plot.id = uuid.uuid4()
    db.execute = AsyncMock(
        side_effect=[ScalarResult(plot), ScalarResult(None)]
    )
    await assistant.create_crop_season(
        str(plot.id),
        assistant.CropSeasonCreateRequest(
            crop="Cà chua",
            variety="Cherry",
            growth_stage="Mới trồng",
            planted_on=date(2026, 8, 10),
            expected_harvest_on=date(2026, 11, 15),
            status="active",
        ),
        db=db,
        current_user={"id": "user-a"},
    )
    season = db.add.call_args.args[0]
    assert season.user_id == "user-a"
    assert season.plot_id == plot.id
    assert season.crop == "Cà chua"
    assert season.status == "active"


@pytest.mark.asyncio
async def test_plot_listing_includes_owned_season_history():
    plot = SimpleNamespace(
        id=uuid.uuid4(),
        farm_profile_id=uuid.uuid4(),
        name="Nhà kính A",
        area_ha=0.4,
        location_note=None,
        latitude=11.941,
        longitude=108.438,
        elevation_m=1500,
        location_accuracy_m=8,
        location_source="device",
        coordinates_updated_at=datetime(2026, 8, 1),
        status="active",
        created_at=datetime(2026, 8, 1),
        updated_at=datetime(2026, 8, 1),
    )
    season = SimpleNamespace(
        id=uuid.uuid4(),
        plot_id=plot.id,
        crop="Cà chua",
        variety="Cherry",
        growth_stage="Ra hoa",
        planted_on=date(2026, 8, 1),
        expected_harvest_on=None,
        status="active",
        ended_at=None,
        created_at=datetime(2026, 8, 1),
        updated_at=datetime(2026, 8, 1),
    )
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[ScalarsResult([plot]), ScalarsResult([season])]
        )
    )

    response = await assistant.list_farm_plots(
        db=db, current_user={"id": "user-a"}
    )

    assert response[0]["name"] == "Nhà kính A"
    assert response[0]["latitude"] == 11.941
    assert response[0]["location_source"] == "device"
    assert response[0]["seasons"][0]["crop"] == "Cà chua"
    statements = [str(call.args[0]) for call in db.execute.await_args_list]
    assert all("user_id" in statement for statement in statements)


@pytest.mark.asyncio
async def test_plot_coordinates_require_a_valid_pair():
    db = SimpleNamespace(execute=AsyncMock())

    with pytest.raises(HTTPException, match="provided together") as error:
        await assistant.create_farm_plot(
            assistant.FarmPlotCreateRequest(name="Thửa A", latitude=11.9),
            db=db,
            current_user={"id": "user-a"},
        )

    assert error.value.status_code == 422
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_owner_can_update_and_clear_plot_coordinates():
    now = datetime(2026, 8, 12, 8, 0)
    plot = SimpleNamespace(
        id=uuid.uuid4(),
        user_id="user-a",
        farm_profile_id=uuid.uuid4(),
        name="Thửa A",
        area_ha=0.5,
        location_note=None,
        latitude=None,
        longitude=None,
        elevation_m=None,
        location_accuracy_m=None,
        location_source=None,
        coordinates_updated_at=None,
        status="active",
        created_at=now,
        updated_at=now,
    )
    db = SimpleNamespace(
        execute=AsyncMock(return_value=ScalarResult(plot)),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )

    response = await assistant.update_farm_plot(
        str(plot.id),
        assistant.FarmPlotUpdateRequest(
            latitude=10.1,
            longitude=106.2,
            location_accuracy_m=12,
            location_source="device",
        ),
        db=db,
        current_user={"id": "user-a"},
    )

    assert response["latitude"] == 10.1
    assert plot.coordinates_updated_at is not None
    assert "farm_plots.user_id" in str(db.execute.await_args.args[0])

    await assistant.update_farm_plot(
        str(plot.id),
        assistant.FarmPlotUpdateRequest(
            latitude=None,
            longitude=None,
            elevation_m=None,
            location_accuracy_m=None,
            location_source=None,
        ),
        db=db,
        current_user={"id": "user-a"},
    )
    assert plot.latitude is None
    assert plot.coordinates_updated_at is None


@pytest.mark.asyncio
async def test_plot_rejects_second_active_crop_season():
    plot = SimpleNamespace(id=uuid.uuid4())
    active = SimpleNamespace(id=uuid.uuid4())
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[ScalarResult(plot), ScalarResult(active)]
        )
    )

    with pytest.raises(HTTPException, match="active crop season") as error:
        await assistant.create_crop_season(
            str(plot.id),
            assistant.CropSeasonCreateRequest(crop="Cà chua", status="active"),
            db=db,
            current_user={"id": "user-a"},
        )

    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_completing_season_pauses_its_active_schedule():
    season = SimpleNamespace(
        id=uuid.uuid4(),
        plot_id=uuid.uuid4(),
        crop="Cà chua",
        variety=None,
        growth_stage="Ra hoa",
        planted_on=date(2026, 5, 1),
        expected_harvest_on=date(2026, 8, 1),
        status="active",
        ended_at=None,
        created_at=datetime(2026, 5, 1),
        updated_at=datetime(2026, 5, 1),
    )
    schedule = _schedule_record()
    schedule.crop_season_id = season.id
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[ScalarResult(season), ScalarsResult([schedule])]
        ),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )

    await assistant.update_crop_season(
        str(season.id),
        assistant.CropSeasonUpdateRequest(status="completed"),
        db=db,
        current_user={"id": "user-a"},
    )

    assert season.status == "completed"
    assert season.ended_at is not None
    assert schedule.status == "paused"
    assert schedule.next_run_at is None


@pytest.mark.asyncio
async def test_changing_active_season_crop_pauses_tomato_monitoring():
    season = SimpleNamespace(
        id=uuid.uuid4(),
        plot_id=uuid.uuid4(),
        crop="Cà chua",
        variety=None,
        growth_stage=None,
        planted_on=None,
        expected_harvest_on=None,
        status="active",
        ended_at=None,
        created_at=datetime(2026, 8, 1),
        updated_at=datetime(2026, 8, 1),
    )
    schedule = _schedule_record()
    schedule.crop_season_id = season.id
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[ScalarResult(season), ScalarsResult([schedule])]
        ),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )

    await assistant.update_crop_season(
        str(season.id),
        assistant.CropSeasonUpdateRequest(crop="Ớt"),
        db=db,
        current_user={"id": "user-a"},
    )

    assert season.crop == "Ớt"
    assert schedule.status == "paused"
    assert schedule.next_run_at is None


@pytest.mark.asyncio
async def test_changing_growth_stage_refreshes_policy_without_pausing_schedule():
    season = SimpleNamespace(
        id=uuid.uuid4(),
        plot_id=uuid.uuid4(),
        crop="Cà chua",
        variety=None,
        growth_stage="Mới trồng",
        planted_on=None,
        expected_harvest_on=None,
        status="active",
        ended_at=None,
        created_at=datetime(2026, 8, 1),
        updated_at=datetime(2026, 8, 1),
    )
    schedule = _schedule_record()
    schedule.crop_season_id = season.id
    original_next_run = schedule.next_run_at
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[ScalarResult(season), ScalarsResult([schedule])]
        ),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )

    response = await assistant.update_crop_season(
        str(season.id),
        assistant.CropSeasonUpdateRequest(growth_stage="Ra hoa"),
        db=db,
        current_user={"id": "user-a"},
    )

    assert response["growth_stage"] == "Ra hoa"
    assert schedule.status == "active"
    assert schedule.next_run_at == original_next_run
    assert schedule.reminder_type == "tomato_mid_season_weather_watch"
    assert "farm_monitoring_schedules.user_id" in str(
        db.execute.await_args_list[1].args[0]
    )


@pytest.mark.asyncio
async def test_non_tomato_season_can_resume_with_matching_policy():
    schedule = _schedule_record()
    schedule.status = "paused"
    season = SimpleNamespace(
        id=schedule.crop_season_id,
        crop="Ớt",
        growth_stage="Ra hoa",
        status="active",
    )
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[ScalarResult(schedule), ScalarResult(season)]
        ),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )

    await assistant.update_monitoring_schedule(
        str(schedule.id),
        assistant.MonitoringScheduleUpdateRequest(status="active"),
        db=db,
        current_user={"id": "user-a"},
    )

    assert schedule.status == "active"
    assert schedule.crop == "Ớt"
    assert schedule.reminder_type == "chili_mid_season_weather_watch"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("plot", "expected_source", "expected_coordinates", "should_geocode"),
    [
        (
            SimpleNamespace(
                latitude=11.941,
                longitude=108.438,
                location_accuracy_m=7,
                elevation_m=1500,
            ),
            "plot_gps",
            {"latitude": 11.941, "longitude": 108.438},
            False,
        ),
        (
            None,
            "province_geocode",
            {"latitude": 11.9, "longitude": 108.4},
            True,
        ),
    ],
)
async def test_worker_persists_observation_prediction_recommendation_and_notice(
    monkeypatch,
    plot,
    expected_source,
    expected_coordinates,
    should_geocode,
):
    now = datetime(2026, 8, 12, 8, 0)
    schedule = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        plot_id=uuid.uuid4(),
        crop_season_id=uuid.uuid4(),
        crop="Lúa",
        province="Lâm Đồng",
        frequency_hours=24,
        notification_scope="in_app",
        next_run_at=now,
        last_run_at=None,
        last_error_code=None,
    )
    added = []

    def add(record):
        added.append(record)

    async def flush():
        for record in added:
            if getattr(record, "id", None) is None:
                record.id = uuid.uuid4()

    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                ScalarResult(None),
                ScalarResult(plot),
                ScalarResult(SimpleNamespace(growth_stage="Ra hoa")),
                ScalarResult(None),
            ]
        ),
        add=Mock(side_effect=add),
        flush=AsyncMock(side_effect=flush),
    )
    monkeypatch.setattr(
        worker, "geocode_province_via_mcp", AsyncMock(return_value=(11.9, 108.4))
    )
    monkeypatch.setattr(
        worker,
        "get_weather_via_mcp",
        AsyncMock(
            return_value={
                "forecast": [
                    {
                        "date": "2026-08-13",
                        "rain_probability": 0.85,
                        "humidity": 91,
                        "temp": 23,
                        "description": "mưa",
                    }
                ]
            }
        ),
    )

    await worker._run_monitoring_schedule(session, schedule, now)

    assert any(isinstance(item, FarmWeatherObservation) for item in added)
    observation = next(
        item for item in added if isinstance(item, FarmWeatherObservation)
    )
    assert observation.inputs["coordinate_source"] == expected_source
    assert observation.inputs["coordinates"] == expected_coordinates
    assert observation.inputs["growth_stage"] == "Ra hoa"
    assert observation.inputs["growth_stage_key"] == "mid_season"
    if should_geocode:
        worker.geocode_province_via_mcp.assert_awaited_once_with("Lâm Đồng")
    else:
        worker.geocode_province_via_mcp.assert_not_awaited()
    assert any(isinstance(item, FarmRiskPrediction) for item in added)
    recommendation = next(
        item for item in added if isinstance(item, FarmRecommendation)
    )
    action = next(item for item in added if isinstance(item, PendingAction))
    notice = next(item for item in added if isinstance(item, Notification))
    assert recommendation.notification_id == notice.id
    assert recommendation.pending_action_id == action.id
    assert recommendation.status == "notified"
    prediction = next(item for item in added if isinstance(item, FarmRiskPrediction))
    assert prediction.policy_version == "rice-stage-mid_season-v1"
    assert prediction.inputs["growth_stage_key"] == "mid_season"
    assert prediction.inputs["policy_sources"]
    assert recommendation.kind == "crop_weather_risk_check"
    assert "lúa" in recommendation.title
    assert action.action_type == "create_task"
    assert action.payload["source"] == "farm_monitoring"
    assert action.expires_at > action.created_at
    assert "không phải chẩn đoán bệnh" in recommendation.body
    assert schedule.last_run_at == now
    assert schedule.next_run_at > now


@pytest.mark.asyncio
async def test_schedule_failure_rolls_back_its_savepoint_and_retries_later(
    monkeypatch, caplog
):
    class Savepoint:
        rolled_back = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, _exc, _traceback):
            self.rolled_back = exc_type is not None
            return False

    savepoint = Savepoint()
    session = SimpleNamespace(begin_nested=lambda: savepoint)
    schedule = SimpleNamespace(
        id=uuid.uuid4(),
        last_error_code=None,
        next_run_at=None,
    )
    now = datetime(2026, 8, 17, 8, 0)

    async def fail_after_flush(_session, _schedule, _now):
        raise RuntimeError("weather provider failed")

    monkeypatch.setattr(worker, "_run_monitoring_schedule", fail_after_flush)

    completed = await worker._run_monitoring_schedule_isolated(
        session, schedule, now
    )

    assert completed is False
    assert savepoint.rolled_back is True
    assert schedule.last_error_code == "weather_monitoring_unavailable"
    assert schedule.next_run_at == now + timedelta(minutes=15)
    assert "weather provider failed" not in caplog.text
    assert caplog.records[-1].error_type == "RuntimeError"


@pytest.mark.asyncio
async def test_notify_reuses_existing_dedupe_record(monkeypatch):
    existing = SimpleNamespace(id=uuid.uuid4())
    session = SimpleNamespace(
        execute=AsyncMock(return_value=ScalarResult(existing)),
        add=Mock(),
    )
    send_push = AsyncMock()
    monkeypatch.setattr(worker, "send_push", send_push)

    notice, created = await worker._notify(
        session,
        "user-a",
        "crop_disease_risk",
        "title",
        "body",
        "dedupe-key",
    )

    assert notice is existing
    assert created is False
    session.add.assert_not_called()
    send_push.assert_not_awaited()


@pytest.mark.asyncio
async def test_notify_persists_push_outbox_without_sending_before_commit(monkeypatch):
    now = datetime(2026, 8, 12, 1, 0)
    device = SimpleNamespace(id=uuid.uuid4(), token="device-token")
    added = []

    def add(record):
        added.append(record)

    async def flush():
        for record in added:
            if getattr(record, "id", None) is None:
                record.id = uuid.uuid4()

    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[ScalarResult(None), ScalarsResult([device])]
        ),
        add=Mock(side_effect=add),
        flush=AsyncMock(side_effect=flush),
    )
    send_push = AsyncMock()
    monkeypatch.setattr(worker, "utc_now_naive", lambda: now)
    monkeypatch.setattr(worker, "send_push", send_push)

    notice, created = await worker._notify(
        session,
        "user-a",
        "crop_disease_risk",
        "title",
        "body",
        "dedupe-key",
        push_enabled=True,
    )

    delivery = next(item for item in added if isinstance(item, NotificationDelivery))
    assert created is True
    assert delivery.notification_id == notice.id
    assert delivery.device_token_id == device.id
    assert delivery.status == "pending"
    assert notice.delivered_at == now
    assert delivery.next_attempt_at == now
    send_push.assert_not_awaited()


class AsyncSessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_push_delivery_retries_then_marks_delivered(monkeypatch):
    now = datetime(2026, 8, 12, 8, 0)
    delivery = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        notification_id=uuid.uuid4(),
        device_token_id=uuid.uuid4(),
        status="pending",
        attempt_count=0,
        next_attempt_at=now,
        last_attempt_at=None,
        delivered_at=None,
        last_error_code=None,
        updated_at=now,
    )
    notice = SimpleNamespace(title="title", body="body")
    device = SimpleNamespace(token="device-token")
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                ScalarsResult([delivery]),
                ScalarResult(notice),
                ScalarResult(device),
            ]
        ),
        add=Mock(),
        commit=AsyncMock(),
    )
    monkeypatch.setattr(worker, "utc_now_naive", lambda: now)
    monkeypatch.setattr(
        worker, "AsyncSessionLocal", lambda: AsyncSessionContext(session)
    )
    monkeypatch.setattr(worker, "send_push", AsyncMock(return_value=False))

    await worker.process_push_deliveries_once()

    assert delivery.status == "retry"
    assert delivery.attempt_count == 1
    assert delivery.next_attempt_at > now
    first_attempt = session.add.call_args.args[0]
    assert isinstance(first_attempt, NotificationDeliveryAttempt)
    assert first_attempt.status == "retry"
    session.commit.assert_awaited_once()

    delivery.next_attempt_at = now
    session.execute = AsyncMock(
        side_effect=[
            ScalarsResult([delivery]),
            ScalarResult(notice),
            ScalarResult(device),
        ]
    )
    worker.send_push = AsyncMock(return_value=True)

    await worker.process_push_deliveries_once()

    assert delivery.status == "delivered"
    assert delivery.attempt_count == 2
    assert delivery.delivered_at == now


@pytest.mark.asyncio
async def test_push_delivery_cancels_when_owned_target_is_missing(monkeypatch):
    now = datetime(2026, 8, 12, 8, 0)
    delivery = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        notification_id=uuid.uuid4(),
        device_token_id=uuid.uuid4(),
        status="pending",
        attempt_count=0,
        next_attempt_at=now,
        last_attempt_at=None,
        delivered_at=None,
        last_error_code=None,
        updated_at=now,
    )
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                ScalarsResult([delivery]),
                ScalarResult(None),
                ScalarResult(None),
            ]
        ),
        add=Mock(),
        commit=AsyncMock(),
    )
    monkeypatch.setattr(worker, "utc_now_naive", lambda: now)
    monkeypatch.setattr(
        worker, "AsyncSessionLocal", lambda: AsyncSessionContext(session)
    )
    send_push = AsyncMock()
    monkeypatch.setattr(worker, "send_push", send_push)

    await worker.process_push_deliveries_once()

    assert delivery.status == "cancelled"
    assert delivery.last_error_code == "delivery_target_unavailable"
    send_push.assert_not_awaited()


@pytest.mark.asyncio
async def test_notification_exposes_owned_pending_recommendation():
    notification = SimpleNamespace(
        id=uuid.uuid4(),
        kind="crop_disease_risk",
        title="Nguy cơ tăng",
        body="Kiểm tra lá",
        created_at=datetime(2026, 8, 12, 8, 0),
        read_at=None,
    )
    recommendation = SimpleNamespace(
        id=uuid.uuid4(),
        notification_id=notification.id,
        pending_action_id=uuid.uuid4(),
        status="notified",
        expires_at=datetime(2026, 8, 13, 8, 0),
    )
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                ScalarsResult([notification]),
                ScalarsResult([recommendation]),
            ]
        )
    )

    response = await assistant.list_notifications(
        db=db, current_user={"id": "user-a"}
    )

    assert response[0]["recommendation"]["pending_action_id"] == str(
        recommendation.pending_action_id
    )
    assert response[0]["created_at"].tzinfo == timezone.utc
    assert response[0]["created_at"].hour == 8
    assert response[0]["read_at"] is None
    statements = [str(call.args[0]) for call in db.execute.await_args_list]
    assert all("user_id" in statement for statement in statements)


@pytest.mark.asyncio
async def test_mark_all_notifications_read_is_scoped_to_current_user():
    result = SimpleNamespace(rowcount=2)
    db = SimpleNamespace(
        execute=AsyncMock(return_value=result),
        commit=AsyncMock(),
    )

    response = await assistant.mark_all_notifications_read(
        db=db,
        current_user={"id": "user-a"},
    )

    assert response == {"status": "read", "updated": 2}
    statement = str(db.execute.await_args.args[0])
    assert "notifications.user_id" in statement
    assert "notifications.read_at IS NULL" in statement
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_unread_notification_count_is_scoped_to_current_user():
    count_result = SimpleNamespace(scalar_one=lambda: 3)
    db = SimpleNamespace(execute=AsyncMock(return_value=count_result))

    response = await assistant.unread_notification_count(
        db=db,
        current_user={"id": "user-a"},
    )

    assert response == {"count": 3}
    statement = str(db.execute.await_args.args[0])
    assert "notifications.user_id" in statement
    assert "notifications.read_at IS NULL" in statement


@pytest.mark.asyncio
async def test_open_task_count_is_scoped_to_current_user():
    count_result = SimpleNamespace(scalar_one=lambda: 4)
    db = SimpleNamespace(execute=AsyncMock(return_value=count_result))

    response = await assistant.open_task_count(
        db=db,
        current_user={"id": "user-a"},
    )

    assert response == {"count": 4}
    statement = str(db.execute.await_args.args[0])
    assert "farm_tasks.user_id" in statement
    assert "farm_tasks.status" in statement


@pytest.mark.asyncio
async def test_due_task_notification_does_not_complete_task(monkeypatch):
    now = datetime(2026, 8, 20, 18, 0)
    task = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        title="Tưới cà chua",
        due_at=now,
        status="open",
    )
    added = []

    async def flush():
        for record in added:
            if getattr(record, "id", None) is None:
                record.id = uuid.uuid4()

    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                ScalarsResult([task]),
                ScalarResult(None),
                ScalarsResult([]),
            ]
        ),
        add=Mock(side_effect=added.append),
        flush=AsyncMock(side_effect=flush),
        commit=AsyncMock(),
    )
    monkeypatch.setattr(worker, "local_now_naive", lambda: now)
    monkeypatch.setattr(
        worker,
        "AsyncSessionLocal",
        lambda: AsyncSessionContext(session),
    )

    await worker.process_due_tasks_once()

    notice = next(item for item in added if isinstance(item, Notification))
    assert notice.kind == "task_due"
    assert notice.body == task.title
    assert task.status == "open"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_confirm_recommendation_creates_task_once_and_audits_acceptance():
    action = SimpleNamespace(
        id=uuid.uuid4(),
        user_id="user-a",
        action_type="create_task",
        payload={
            "title": "Kiểm tra lá cà chua tại ruộng",
            "description": "Kiểm tra hai mặt lá",
            "due_at": "2026-08-13T07:00:00",
        },
        status="pending",
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=6),
    )
    recommendation = SimpleNamespace(
        pending_action_id=action.id,
        user_id="user-a",
        status="notified",
        task_id=None,
        resolved_at=None,
    )
    added = []

    def add(record):
        added.append(record)

    async def flush():
        for record in added:
            if getattr(record, "id", None) is None:
                record.id = uuid.uuid4()

    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[ScalarResult(recommendation), ScalarResult(action)]
        ),
        add=Mock(side_effect=add),
        flush=AsyncMock(side_effect=flush),
        commit=AsyncMock(),
    )

    response = await assistant.confirm_action(
        str(action.id), db=db, current_user={"id": "user-a"}
    )

    task = next(item for item in added if isinstance(item, FarmTask))
    assert action.status == "confirmed"
    assert recommendation.status == "accepted"
    assert recommendation.task_id == task.id
    assert response["record_id"] == str(task.id)
    db.commit.assert_awaited_once()
    assert "FOR UPDATE" in str(db.execute.await_args_list[0].args[0])
    assert "FOR UPDATE" in str(db.execute.await_args_list[1].args[0])


@pytest.mark.asyncio
async def test_cancel_recommendation_does_not_create_task():
    action = SimpleNamespace(id=uuid.uuid4(), status="pending")
    recommendation = SimpleNamespace(
        status="notified", resolved_at=None
    )
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[ScalarResult(recommendation), ScalarResult(action)]
        ),
        commit=AsyncMock(),
    )

    response = await assistant.cancel_action(
        str(action.id), db=db, current_user={"id": "user-a"}
    )

    assert response == {"status": "cancelled"}
    assert action.status == "cancelled"
    assert recommendation.status == "dismissed"
    db.commit.assert_awaited_once()
    assert "FOR UPDATE" in str(db.execute.await_args_list[0].args[0])
    assert "FOR UPDATE" in str(db.execute.await_args_list[1].args[0])


@pytest.mark.asyncio
async def test_expiry_sweep_audits_recommendation_and_pending_action():
    now = datetime(2026, 8, 12, 8, 0)
    action = SimpleNamespace(id=uuid.uuid4(), user_id="user-a", status="pending")
    recommendation = SimpleNamespace(
        id=uuid.uuid4(),
        user_id="user-a",
        pending_action_id=action.id,
        status="notified",
        expires_at=now - timedelta(minutes=1),
        resolved_at=None,
    )
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[ScalarsResult([recommendation]), ScalarResult(action)]
        )
    )

    expired = await worker._expire_recommendations(session, now)

    assert expired == 1
    assert recommendation.status == "expired"
    assert recommendation.resolved_at == now
    assert action.status == "expired"
    statement = str(session.execute.await_args_list[1].args[0])
    assert "pending_actions.user_id" in statement
    assert "FOR UPDATE" in statement
