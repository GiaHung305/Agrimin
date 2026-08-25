from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Permission, require_permission
from app.core.db import get_db
from app.persistence.models import (
    Notification,
    NotificationDelivery,
    NotificationDeliveryAttempt,
    WorkerFailure,
)
from app.workers.health import read_worker_health

router = APIRouter(prefix="/operations", tags=["operations"])
operations_access = require_permission(Permission.OPERATIONS_VIEW)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


@router.get("/worker-dashboard")
async def worker_dashboard(
    db: AsyncSession = Depends(get_db),
    _current_user: dict = Depends(operations_access),
) -> dict:
    """Admin-only operational snapshot without exposing tokens or message bodies."""
    try:
        heartbeat = await read_worker_health()
    except Exception:
        heartbeat = {"status": "degraded", "cycles": {}, "error": "heartbeat_unavailable"}

    delivery_rows = (
        await db.execute(
            select(NotificationDelivery.status, func.count(NotificationDelivery.id))
            .group_by(NotificationDelivery.status)
        )
    ).all()
    counts = {status: count for status, count in delivery_rows}
    for status in ("pending", "retry", "delivered", "failed", "cancelled"):
        counts.setdefault(status, 0)

    attempts = (
        await db.execute(
            select(NotificationDeliveryAttempt, Notification.title)
            .join(
                NotificationDelivery,
                NotificationDelivery.id == NotificationDeliveryAttempt.delivery_id,
            )
            .join(Notification, Notification.id == NotificationDelivery.notification_id)
            .order_by(NotificationDeliveryAttempt.created_at.desc())
            .limit(30)
        )
    ).all()
    failures = (
        await db.execute(
            select(WorkerFailure)
            .where(
                WorkerFailure.created_at
                >= datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
            )
            .order_by(WorkerFailure.created_at.desc())
            .limit(30)
        )
    ).scalars().all()

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "worker": heartbeat,
        "deliveries": {
            "counts": counts,
            "recent_attempts": [
                {
                    "delivery_id": str(attempt.delivery_id),
                    "notification_title": title,
                    "attempt_number": attempt.attempt_number,
                    "status": attempt.status,
                    "error_code": attempt.error_code,
                    "created_at": _iso(attempt.created_at),
                }
                for attempt, title in attempts
            ],
        },
        "recent_failures": [
            {
                "id": str(item.id),
                "cycle": item.cycle_name,
                "error_code": item.error_code,
                "consecutive_failures": item.consecutive_failures,
                "created_at": _iso(item.created_at),
            }
            for item in failures
        ],
    }
