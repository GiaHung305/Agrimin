import re
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.repository.models import PendingAction
from app.workflow.state import AgentState


def _proposal_from_question(question: str) -> tuple[str, dict] | None:
    normalized = question.casefold()
    if any(phrase in normalized for phrase in ("nhắc tôi", "tạo việc", "lập việc")):
        return "create_task", {"title": question.strip(), "description": "Việc do Trợ lý AgriMind đề xuất", "due_at": None}
    if any(phrase in normalized for phrase in ("ghi nhật ký", "lưu nhật ký", "nhật ký canh tác")):
        return "create_log", {"title": "Nhật ký canh tác", "content": question.strip()}
    return None


_LOCAL_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _normalized(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFD", value.casefold())
        if unicodedata.category(char) != "Mn"
    ).replace("đ", "d")


def _is_task_request(question: str) -> bool:
    normalized = _normalized(question)
    return any(phrase in normalized for phrase in ("nhac toi", "tao viec", "lap viec"))


def _parse_due_at(question: str, now: datetime | None = None) -> datetime | None:
    """Parse supported Vietnamese date/time forms; never guess a reminder schedule."""
    normalized = _normalized(question)
    current = now or datetime.now(_LOCAL_TZ)
    time_match = re.search(r"\b(\d{1,2})\s*(?:gio|h)(?:\s*(\d{1,2}))?\b", normalized)
    if not time_match:
        return None
    hour, minute = int(time_match.group(1)), int(time_match.group(2) or 0)
    if hour > 23 or minute > 59:
        return None
    if "ngay mai" in normalized:
        target_date = (current + timedelta(days=1)).date()
    elif "hom nay" in normalized:
        target_date = current.date()
    else:
        match = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{4}))?\b", normalized)
        if not match:
            return None
        day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3) or current.year)
        try:
            target_date = datetime(year, month, day).date()
        except ValueError:
            return None
    return datetime.combine(target_date, datetime.min.time()).replace(hour=hour, minute=minute)


def _previous_task_request(history: list[dict]) -> str | None:
    for turn in reversed(history):
        if turn.get("role") != "user":
            continue
        if _is_task_request(turn.get("content", "")):
            return turn["content"]
    return None


async def action_proposal_node(state: AgentState, db: AsyncSession) -> AgentState:
    """Create a reversible proposal; the API applies it only after confirmation."""
    question = state["question"]
    due_at = _parse_due_at(question)
    if _is_task_request(question):
        # A task without a deadline cannot satisfy a reminder request.
        proposal = None if due_at is None else ("create_task", {
            "title": question.strip(),
            "description": "Việc do Trợ lý AgriMind đề xuất",
            "due_at": due_at.isoformat(),
        })
    else:
        proposal = _proposal_from_question(question)
        if proposal is None and due_at is not None:
            prior_task = _previous_task_request(state.get("context", {}).get("conversation_history", []))
            if prior_task:
                proposal = ("create_task", {
                    "title": prior_task.strip(),
                    "description": "Việc do Trợ lý AgriMind đề xuất",
                    "due_at": due_at.isoformat(),
                })
    if proposal is None:
        state["pending_action"] = None
        return state
    action_type, payload = proposal
    action = PendingAction(
        user_id=state["user_id"],
        conversation_id=state["conversation_id"],
        action_type=action_type,
        payload=payload,
        expires_at=datetime.utcnow() + timedelta(minutes=15),
    )
    db.add(action)
    await db.commit()
    state["pending_action"] = {"id": str(action.id), "type": action_type, "payload": payload, "expires_at": action.expires_at.isoformat()}
    return state
