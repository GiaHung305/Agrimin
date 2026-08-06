import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.workflow.nodes.action_proposal import _is_task_request, _parse_due_at, _previous_task_request


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
