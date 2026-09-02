import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.workflow.question_freshness import (
    casual_message_kind,
    has_weather_intent,
    is_realtime_sensitive_question,
    is_weather_only_question,
)


@pytest.mark.parametrize(
    "question",
    [
        "Thời tiết Đắk Lắk hôm nay thế nào?",
        "Thoi tiet Dak Lak ngay mai the nao?",
        "Hom nay co mua khong?",
        "Luong mua tuan nay bao nhieu?",
        "Nhiệt độ và độ ẩm hiện tại là bao nhiêu?",
        "Bao so 5 co do bo khong?",
        "Toc do gio giat hien tai?",
    ],
)
def test_weather_intent_supports_accented_and_unaccented_vietnamese(question):
    assert has_weather_intent(question)
    assert is_realtime_sensitive_question(question)


@pytest.mark.parametrize(
    "question",
    [
        "Mua phân bón ở đâu?",
        "Bao nhiêu ngày thì cà chua thu hoạch?",
        "Cách tỉa cành cà chua",
        "So sánh hai giống lúa",
    ],
)
def test_weather_intent_avoids_common_unaccented_homonyms(question):
    assert not has_weather_intent(question)
    assert not is_realtime_sensitive_question(question)


@pytest.mark.parametrize(
    "question",
    [
        "Giá trị mới nhất là gì?",
        "Hien tai cay dang o giai doan nao?",
        "Tuan toi nen xuong giong khi nao?",
        "Sự việc vừa xảy ra có ảnh hưởng không?",
    ],
)
def test_temporal_language_bypasses_cache_even_without_weather(question):
    assert is_realtime_sensitive_question(question)


@pytest.mark.parametrize(
    "question",
    [
        "Thời tiết Đà Lạt hôm nay thế nào?",
        "Ngày mai ở Hà Nội có mưa không?",
        "Nhiệt độ và độ ẩm hiện tại là bao nhiêu?",
    ],
)
def test_weather_only_question_recognizes_direct_forecasts(question):
    assert is_weather_only_question(question)


@pytest.mark.parametrize(
    "question",
    [
        "Mưa ảnh hưởng tưới cà phê thế nào?",
        "Thời tiết này có nên phun thuốc không?",
        "Độ ẩm cao có làm cây cà chua dễ bệnh không?",
    ],
)
def test_weather_only_question_keeps_farming_decisions_in_grounded_flow(question):
    assert not is_weather_only_question(question)


@pytest.mark.parametrize(
    "question,expected",
    [
        ("Xin chào!", "greeting"),
        ("Chao AgriMind", "greeting"),
        ("Cảm ơn bạn nhé", "thanks"),
        ("Cảm ơn bạn", "thanks"),
        ("OK", "acknowledgement"),
        ("Được rồi", "acknowledgement"),
    ],
)
def test_casual_message_kind_is_narrow_and_deterministic(question, expected):
    assert casual_message_kind(question) == expected


@pytest.mark.parametrize(
    "question",
    [
        "Chào bạn, cà chua bị héo thì làm sao?",
        "Được rồi, pha thuốc thế nào?",
        "Cảm ơn, ngày mai nhắc tôi tưới cây nhé",
    ],
)
def test_casual_message_kind_does_not_swallow_real_requests(question):
    assert casual_message_kind(question) is None
