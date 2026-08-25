import json
from datetime import datetime, timezone

from app.core.config import settings
from app.core.redis_client import redis_client

WORKER_NAME = "assistant"
WORKER_CYCLES = ("task_reminders", "farm_monitoring", "push_deliveries")
HEARTBEAT_PREFIX = f"agrimind:worker:{WORKER_NAME}"


def _heartbeat_key(cycle_name: str) -> str:
    return f"{HEARTBEAT_PREFIX}:{cycle_name}"


async def record_heartbeat(
    cycle_name: str,
    status: str,
    *,
    consecutive_failures: int = 0,
    error_code: str | None = None,
) -> None:
    payload = {
        "worker": WORKER_NAME,
        "cycle": cycle_name,
        "status": status,
        "consecutive_failures": consecutive_failures,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if error_code:
        payload["error_code"] = error_code
    await redis_client.set(
        _heartbeat_key(cycle_name),
        json.dumps(payload),
        ex=settings.assistant_worker_heartbeat_ttl_seconds,
    )


async def read_worker_health() -> dict:
    now = datetime.now(timezone.utc)
    cycles: dict[str, dict] = {}
    healthy = True
    for cycle_name in WORKER_CYCLES:
        raw = await redis_client.get(_heartbeat_key(cycle_name))
        if raw is None:
            cycles[cycle_name] = {"status": "missing"}
            healthy = False
            continue
        try:
            payload = json.loads(raw)
            updated_at = datetime.fromisoformat(payload["updated_at"])
            age_seconds = max(0, int((now - updated_at).total_seconds()))
            cycle_healthy = (
                payload.get("status") in {"running", "ok"}
                and age_seconds <= settings.assistant_worker_heartbeat_ttl_seconds
            )
            cycles[cycle_name] = {
                "status": payload.get("status", "unknown"),
                "age_seconds": age_seconds,
                "consecutive_failures": payload.get("consecutive_failures", 0),
            }
            if payload.get("error_code"):
                cycles[cycle_name]["error_code"] = payload["error_code"]
            healthy = healthy and cycle_healthy
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            cycles[cycle_name] = {"status": "invalid"}
            healthy = False

    return {
        "status": "ok" if healthy else "degraded",
        "worker": WORKER_NAME,
        "checked_at": now.isoformat(),
        "heartbeat_ttl_seconds": settings.assistant_worker_heartbeat_ttl_seconds,
        "cycles": cycles,
    }
