import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.workflow.nodes.action_proposal import (
    _is_task_request,
    _parse_due_at,
    _previous_task_request,
    analyze_action_request,
    detect_action_intent,
)


def test_reminder_requires_both_date_and_time():
    now = datetime(2026, 8, 6, 10, 0)
    assert _parse_due_at("Nhắc tôi kiểm tra ruộng lúa", now) is None
    assert _parse_due_at("Nhắc tôi kiểm tra ruộng lúa lúc 7 giờ", now) is None


def test_task_intent_accepts_vietnamese_diacritics():
    assert _is_task_request("Nhắc tôi kiểm tra ruộng lúa")


def test_reminder_parses_tomorrow_with_time():
    now = datetime(2026, 8, 6, 10, 0)
    due_at = _parse_due_at("lúc 7 giờ 30 ngày mai", now)
    assert due_at == datetime(2026, 8, 7, 7, 30)


def test_reminder_parses_numeric_date_with_time():
    now = datetime(2026, 8, 6, 10, 0)
    due_at = _parse_due_at("nhắc tôi lúc 18h ngày 08/08", now)
    assert due_at == datetime(2026, 8, 8, 18, 0)


def test_follow_up_uses_previous_task_request():
    history = [
        {"role": "user", "content": "Nhắc tôi kiểm tra ruộng lúa"},
        {"role": "assistant", "content": "Bạn muốn nhắc lúc nào?"},
    ]
    assert _previous_task_request(history) == "Nhắc tôi kiểm tra ruộng lúa"


def test_time_follow_up_combines_with_previous_task_date():
    history = [
        {"role": "user", "content": "Mai nhắc mình tưới cây nhé"},
        {"role": "assistant", "content": "Bạn muốn mình nhắc lúc mấy giờ?"},
    ]
    action = analyze_action_request(
        "6 giờ chiều",
        history,
        now=datetime(2026, 8, 6, 10, 0),
    )

    assert action["complete"] is True
    assert action["title"] == "Tưới cây"
    assert action["due_at"] == "2026-08-07T18:00:00"


def test_date_follow_up_combines_with_previous_task_time():
    history = [
        {"role": "user", "content": "Nhắc mình tưới cây lúc 6 giờ chiều"},
        {"role": "assistant", "content": "Bạn muốn mình nhắc vào ngày nào?"},
    ]
    action = analyze_action_request(
        "Ngày mai nhé",
        history,
        now=datetime(2026, 8, 6, 10, 0),
    )

    assert action["complete"] is True
    assert action["title"] == "Tưới cây"
    assert action["due_at"] == "2026-08-07T18:00:00"


@pytest.mark.parametrize(
    "question",
    [
        "Báo mình tưới rau lúc 6h30 sáng mai nhé",
        "Lên lịch kiểm tra vườn vào 18 giờ ngày mai",
        "Đặt lời nhắc bón phân lúc 7 giờ sáng ngày kia",
        "Đừng quên nhắc tôi thu hoạch lúc 5 giờ chiều mai",
        "Hẹn giờ 8h sáng mai kiểm tra sâu bệnh",
        "Nhớ 7h sáng mai kiểm tra sâu bệnh nha",
        "Remind me to water the tomatoes at 7h tomorrow",
    ],
)
def test_task_intent_accepts_natural_phrasing(question):
    assert detect_action_intent(question) == "create_task"


@pytest.mark.parametrize(
    "question",
    [
        "Cho tôi xem lịch công việc",
        "Lịch thời tiết ngày mai thế nào?",
        "Có nên tưới rau lúc 6 giờ sáng không?",
    ],
)
def test_information_queries_are_not_misread_as_task_creation(question):
    assert detect_action_intent(question) == "none"


def test_reminder_parses_colon_time_and_part_of_day():
    now = datetime(2026, 8, 6, 10, 0)
    due_at = _parse_due_at("Báo mình tưới rau lúc 6:30 tối mai", now)
    assert due_at == datetime(2026, 8, 7, 18, 30)


def test_reminder_parses_day_after_tomorrow():
    now = datetime(2026, 8, 6, 10, 0)
    due_at = _parse_due_at("Hẹn 7h sáng ngày mốt kiểm tra vườn", now)
    assert due_at == datetime(2026, 8, 8, 7, 0)


def test_action_analysis_asks_only_for_missing_time():
    now = datetime(2026, 8, 6, 10, 0)
    action = analyze_action_request(
        "Mai nhớ nhắc mình tưới cây nhé",
        now=now,
    )
    assert action["intent"] == "create_task"
    assert action["complete"] is False
    assert action["missing_fields"] == ["time"]


def test_action_analysis_normalizes_title_and_due_time():
    now = datetime(2026, 8, 6, 10, 0)
    action = analyze_action_request(
        "Tạo lịch 6 giờ tối ngày mai thông báo tưới cây nhé",
        now=now,
    )
    assert action["complete"] is True
    assert action["title"] == "Tưới cây"
    assert action["due_at"] == "2026-08-07T18:00:00"


def test_action_analysis_handles_time_before_request_phrase():
    now = datetime(2026, 8, 6, 10, 0)
    action = analyze_action_request(
        "Mai 6 giờ chiều nhắc tôi tưới cà chua",
        now=now,
    )
    assert action["complete"] is True
    assert action["title"] == "Tưới cà chua"


def test_action_analysis_removes_conversational_filler_from_title():
    now = datetime(2026, 8, 6, 10, 0)
    action = analyze_action_request(
        "Báo mình lúc 8 giờ ngày mai là đi thăm vườn",
        now=now,
    )
    assert action["title"] == "Đi thăm vườn"
