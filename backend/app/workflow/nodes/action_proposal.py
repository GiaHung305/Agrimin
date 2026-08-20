import re
import unicodedata
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.repository.models import PendingAction
from app.workflow.state import AgentState


ActionIntent = Literal["none", "create_task", "create_log"]
_LOCAL_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

_TASK_PATTERNS = (
    re.compile(r"\b(?:nhac|bao)\s+(?:toi|minh|em|anh|chi)\b"),
    re.compile(
        r"\b(?:tao|dat|len|lap|them|ghi)\s+(?:mot\s+)?"
        r"(?:lich|viec|cong viec|lich nhac)\b"
    ),
    re.compile(r"\b(?:hen gio|hen lich|dat loi nhac|tao loi nhac)\b"),
    re.compile(
        r"\b(?:nho|dung quen)\b.{0,80}\b"
        r"(?:nhac|bao|lam|tuoi|bon|kiem tra|thu hoach)\b"
    ),
    re.compile(r"\b(?:remind me|set (?:a )?reminder|add (?:a )?task)\b"),
)
_LOG_PATTERNS = (
    re.compile(r"\b(?:ghi|luu|them|tao)\s+(?:vao\s+)?nhat ky\b"),
    re.compile(r"\bnhat ky canh tac\b"),
    re.compile(r"\b(?:ghi chep|luu lai)\s+(?:viec|hoat dong|lan)\b"),
)
_INFORMATION_PATTERNS = (
    "co nen",
    "tai sao",
    "the nao",
    "lam sao",
    "tu van",
    "huong dan",
    "du bao",
    "thoi tiet",
    "bao nhieu",
    "la gi",
    "cho biet",
)


def _normalized(value: str) -> str:
    normalized = "".join(
        char
        for char in unicodedata.normalize("NFD", value.casefold())
        if unicodedata.category(char) != "Mn"
    ).replace("đ", "d")
    return " ".join(normalized.split())


def detect_action_intent(question: str) -> ActionIntent:
    """Recognize common Vietnamese action requests without exact phrasing."""
    normalized = _normalized(question)
    if any(pattern.search(normalized) for pattern in _LOG_PATTERNS):
        return "create_log"
    if any(pattern.search(normalized) for pattern in _TASK_PATTERNS):
        return "create_task"
    return "none"


def _is_task_request(question: str) -> bool:
    return detect_action_intent(question) == "create_task"


def is_pure_action_request(question: str, intent: ActionIntent) -> bool:
    if intent == "none":
        return False
    normalized = _normalized(question)
    return not any(pattern in normalized for pattern in _INFORMATION_PATTERNS)


def _parse_time(question: str) -> tuple[int, int] | None:
    normalized = _normalized(question)
    match = re.search(
        r"\b(\d{1,2})\s*(?::|h)\s*(\d{1,2})?\s*"
        r"(sang|trua|chieu|toi)?\b",
        normalized,
    )
    if match is None:
        match = re.search(
            r"\b(\d{1,2})\s*gio(?:\s*(\d{1,2}))?\s*"
            r"(sang|trua|chieu|toi)?\b",
            normalized,
        )
    if match is None:
        match = re.search(
            r"\b(?:luc|vao|khoang)\s*(\d{1,2})\s*"
            r"(sang|trua|chieu|toi)\b",
            normalized,
        )
        if match is None:
            return None
        hour, minute, period = int(match.group(1)), 0, match.group(2)
    else:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        period = match.group(3)

    if minute > 59 or hour > 23:
        return None
    if period in {"chieu", "toi"} and 1 <= hour <= 11:
        hour += 12
    elif period == "trua" and 1 <= hour <= 10:
        hour += 12
    elif period == "sang" and hour == 12:
        hour = 0
    return hour, minute


def _weekday_date(normalized: str, current: datetime):
    weekdays = {
        "thu 2": 0,
        "thu hai": 0,
        "thu 3": 1,
        "thu ba": 1,
        "thu 4": 2,
        "thu tu": 2,
        "thu 5": 3,
        "thu nam": 3,
        "thu 6": 4,
        "thu sau": 4,
        "thu 7": 5,
        "thu bay": 5,
        "chu nhat": 6,
    }
    matched = next(
        ((label, value) for label, value in weekdays.items() if label in normalized),
        None,
    )
    if matched is None:
        return None
    _, target_weekday = matched
    days_ahead = (target_weekday - current.weekday()) % 7
    if "tuan sau" in normalized:
        days_ahead += 7
    return (current + timedelta(days=days_ahead)).date()


def _parse_date(question: str, current: datetime):
    normalized = _normalized(question)
    if any(value in normalized for value in ("ngay kia", "ngay mot")):
        return (current + timedelta(days=2)).date()
    if re.search(r"\b(?:ngay mai|mai)\b", normalized):
        return (current + timedelta(days=1)).date()
    if any(value in normalized for value in ("hom nay", "bay gio")):
        return current.date()

    numeric = re.search(
        r"\b(?:ngay\s*)?(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b",
        normalized,
    )
    if numeric:
        day, month = int(numeric.group(1)), int(numeric.group(2))
        raw_year = numeric.group(3)
        year = int(raw_year) if raw_year else current.year
        if raw_year and len(raw_year) == 2:
            year += 2000
        try:
            target = datetime(year, month, day).date()
        except ValueError:
            return None
        if raw_year is None and target < current.date():
            try:
                target = datetime(year + 1, month, day).date()
            except ValueError:
                return None
        return target

    return _weekday_date(normalized, current)


def _parse_due_at(question: str, now: datetime | None = None) -> datetime | None:
    """Parse common Vietnamese date/time forms without inventing missing data."""
    current = now or datetime.now(_LOCAL_TZ)
    parsed_time = _parse_time(question)
    target_date = _parse_date(question, current)
    if parsed_time is None or target_date is None:
        return None
    hour, minute = parsed_time
    due_at = datetime.combine(target_date, datetime.min.time()).replace(
        hour=hour, minute=minute
    )
    return due_at if due_at > current.replace(tzinfo=None) else None


def _previous_task_request(history: list[dict]) -> str | None:
    for turn in reversed(history):
        if turn.get("role") != "user":
            continue
        content = str(turn.get("content", ""))
        if _is_task_request(content):
            return content
    return None


def _task_title(question: str) -> str:
    value = re.sub(
        r"^\s*(?:(?:bạn|ban)\s+ơi\s*)?"
        r"(?:(?:hãy|hay|vui lòng|vui long|làm ơn|lam on|giúp tôi|giup toi)\s*)?"
        r"(?:(?:nhắc|nhac|báo|bao)\s+(?:tôi|toi|mình|minh)\s*|"
        r"(?:tạo|tao|đặt|dat|lên|len|lập|lap|thêm|them)\s+"
        r"(?:một\s+|mot\s+)?(?:lịch nhắc|lich nhac|lịch|lich|việc|viec|"
        r"công việc|cong viec)\s*)",
        "",
        question,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"\b(?:lúc|luc|vào|vao|khoảng|khoang)?\s*\d{1,2}\s*"
        r"(?:(?::|h)\s*\d{0,2}|(?:giờ|gio)(?:\s*\d{1,2})?)\s*"
        r"(?:sáng|sang|trưa|trua|chiều|chieu|tối|toi)?\b",
        " ",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"\b(?:hôm nay|hom nay|ngày mai|ngay mai|mai|ngày kia|ngay kia|"
        r"ngày mốt|ngay mot)\b",
        " ",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"\b(?:(?:nhắc|nhac|báo|bao)\s+(?:tôi|toi|mình|minh|em|anh|chị|chi)|"
        r"thông báo|thong bao|đừng quên|dung quen|nhớ|nho|hẹn giờ|hen gio|"
        r"hẹn lịch|hen lich)\b",
        " ",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"\b(?:(?:ngày|ngay)\s*)?\d{1,2}[/-]\d{1,2}"
        r"(?:[/-]\d{2,4})?\b|\b(?:thứ|thu)\s*(?:2|3|4|5|6|7|hai|ba|"
        r"tư|tu|năm|nam|sáu|sau|bảy|bay)\b|\bchủ nhật|chu nhat\b",
        " ",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"^\s*(?:để|de|thông báo|thong bao|nhắc|nhac)\s+",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"^\s*(?:vào|vao|lúc|luc|ngày|ngay|là|la|rằng|rang)\s+",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"\s+(?:nhé|nhe|nha|giúp tôi|giup toi|với|voi)\s*[.!?]*$",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = " ".join(value.strip(" ,.-").split())
    if not value:
        return "Công việc nông trại"
    return value[0].upper() + value[1:]


def analyze_action_request(
    question: str,
    history: list[dict] | None = None,
    *,
    planner_intent: ActionIntent = "none",
    now: datetime | None = None,
) -> dict:
    """Build one normalized action contract shared by prompts and persistence."""
    current = now or datetime.now(_LOCAL_TZ)
    local_intent = detect_action_intent(question)
    intent: ActionIntent = local_intent if local_intent != "none" else planner_intent
    source_question = question
    schedule_question = question

    has_schedule_detail = (
        _parse_time(question) is not None
        or _parse_date(question, current) is not None
    )
    if intent == "none" and has_schedule_detail:
        previous = _previous_task_request(history or [])
        if previous:
            intent = "create_task"
            source_question = previous
            schedule_question = f"{previous} {question}"

    due_at = _parse_due_at(schedule_question, current)

    if intent == "create_log":
        return {
            "intent": intent,
            "complete": True,
            "title": "Nhật ký canh tác",
            "content": question.strip(),
            "missing_fields": [],
            "pure_action": is_pure_action_request(question, intent),
        }
    if intent != "create_task":
        return {"intent": "none", "complete": False, "missing_fields": []}

    missing_fields = []
    if _parse_date(schedule_question, current) is None:
        missing_fields.append("date")
    if _parse_time(schedule_question) is None:
        missing_fields.append("time")
    if not missing_fields and due_at is None:
        missing_fields.append("future_time")
    return {
        "intent": intent,
        "complete": due_at is not None,
        "title": _task_title(source_question),
        "description": f"Yêu cầu ban đầu: {source_question.strip()}",
        "due_at": due_at.isoformat() if due_at else None,
        "missing_fields": missing_fields,
        "pure_action": is_pure_action_request(source_question, intent),
    }


async def action_proposal_node(state: AgentState, db: AsyncSession) -> AgentState:
    """Create a reversible proposal; only the owner can confirm it later."""
    action = state.get("context", {}).get("action_request") or analyze_action_request(
        state["question"],
        state.get("context", {}).get("conversation_history", []),
        planner_intent=(state.get("plan") or {}).get("action_intent", "none"),
    )
    if not action.get("complete"):
        state["pending_action"] = None
        return state

    if action["intent"] == "create_task":
        action_type = "create_task"
        payload = {
            "title": action["title"],
            "description": action["description"],
            "due_at": action["due_at"],
        }
    elif action["intent"] == "create_log":
        action_type = "create_log"
        payload = {"title": action["title"], "content": action["content"]}
    else:
        state["pending_action"] = None
        return state

    pending = PendingAction(
        user_id=state["user_id"],
        conversation_id=state["conversation_id"],
        action_type=action_type,
        payload=payload,
        expires_at=datetime.utcnow() + timedelta(minutes=15),
    )
    db.add(pending)
    await db.commit()
    state["pending_action"] = {
        "id": str(pending.id),
        "type": action_type,
        "payload": payload,
        "expires_at": pending.expires_at.isoformat(),
    }
    return state
