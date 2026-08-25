import os
import sys
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.workers import assistant_worker as worker
from app.workers import health


def test_worker_backoff_is_bounded(monkeypatch):
    monkeypatch.setattr(worker.settings, "assistant_worker_poll_seconds", 10)
    monkeypatch.setattr(worker.settings, "assistant_worker_max_backoff_seconds", 60)

    assert worker._cycle_delay(0) == 10
    assert worker._cycle_delay(1) == 10
    assert worker._cycle_delay(2) == 20
    assert worker._cycle_delay(20) == 60


@pytest.mark.asyncio
async def test_periodic_cycle_records_success_and_stops(monkeypatch):
    stop_event = worker.asyncio.Event()

    async def operation():
        stop_event.set()

    heartbeat = AsyncMock()
    monkeypatch.setattr(worker, "_safe_record_heartbeat", heartbeat)

    await worker._run_periodically(
        operation,
        "task_reminders",
        "cycle failed",
        stop_event,
    )

    assert heartbeat.await_args_list[0].args[:2] == (
        "task_reminders",
        "running",
    )
    assert heartbeat.await_args_list[1].args[:2] == ("task_reminders", "ok")


@pytest.mark.asyncio
async def test_periodic_cycle_times_out_and_reports_failure(monkeypatch):
    stop_event = worker.asyncio.Event()
    monkeypatch.setattr(
        worker.settings,
        "assistant_worker_operation_timeout_seconds",
        0.01,
    )

    async def operation():
        try:
            await worker.asyncio.sleep(60)
        finally:
            stop_event.set()

    heartbeat = AsyncMock()
    failure_history = AsyncMock()
    monkeypatch.setattr(worker, "_safe_record_heartbeat", heartbeat)
    monkeypatch.setattr(worker, "_safe_record_failure", failure_history)

    await worker._run_periodically(
        operation,
        "push_deliveries",
        "cycle failed",
        stop_event,
    )

    failed = heartbeat.await_args_list[1]
    assert failed.args[:2] == ("push_deliveries", "failed")
    assert failed.kwargs["consecutive_failures"] == 1
    assert failed.kwargs["error_code"] == "TimeoutError"
    failure_history.assert_awaited_once_with("push_deliveries", "TimeoutError", 1)


@pytest.mark.asyncio
async def test_cycle_lock_skips_duplicate_worker(monkeypatch):
    operation = AsyncMock()
    result = Mock()
    result.scalar_one.return_value = False
    session = AsyncMock()
    session.execute.return_value = result

    class Context:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_):
            return None

    monkeypatch.setattr(worker, "AsyncSessionLocal", lambda: Context())

    await worker._run_with_cycle_lock(operation, "task_reminders")

    operation.assert_not_awaited()


@pytest.mark.asyncio
async def test_worker_health_requires_all_fresh_cycles(monkeypatch):
    now = datetime.now(timezone.utc).isoformat()
    payloads = [
        json.dumps(
            {
                "status": "ok",
                "updated_at": now,
                "consecutive_failures": 0,
            }
        )
        for _ in health.WORKER_CYCLES
    ]
    get = AsyncMock(side_effect=payloads)
    monkeypatch.setattr(health.redis_client, "get", get)

    snapshot = await health.read_worker_health()

    assert snapshot["status"] == "ok"
    assert set(snapshot["cycles"]) == set(health.WORKER_CYCLES)


@pytest.mark.asyncio
async def test_worker_health_is_degraded_when_heartbeat_is_missing(monkeypatch):
    monkeypatch.setattr(health.redis_client, "get", AsyncMock(return_value=None))

    snapshot = await health.read_worker_health()

    assert snapshot["status"] == "degraded"
    assert all(cycle["status"] == "missing" for cycle in snapshot["cycles"].values())
