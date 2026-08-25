import os
import sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.api.routes import operations


class Rows:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class Scalars:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return self

    def all(self):
        return self.values


@pytest.mark.asyncio
async def test_worker_dashboard_summarizes_delivery_and_failure_history(monkeypatch):
    now = datetime(2026, 8, 22, 8, 0)
    attempt = SimpleNamespace(
        delivery_id=uuid4(),
        attempt_number=2,
        status="retry",
        error_code="push_delivery_failed",
        created_at=now,
    )
    failure = SimpleNamespace(
        id=uuid4(),
        cycle_name="push_deliveries",
        error_code="TimeoutError",
        consecutive_failures=2,
        created_at=now,
    )
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                Rows([("delivered", 4), ("retry", 1)]),
                Rows([(attempt, "Tưới cây")]),
                Scalars([failure]),
            ]
        )
    )
    monkeypatch.setattr(
        operations,
        "read_worker_health",
        AsyncMock(return_value={"status": "ok", "cycles": {}}),
    )

    payload = await operations.worker_dashboard(
        db=db,
        _current_user={"id": "admin-id"},
    )

    assert payload["deliveries"]["counts"]["delivered"] == 4
    assert payload["deliveries"]["counts"]["failed"] == 0
    assert payload["deliveries"]["recent_attempts"][0]["status"] == "retry"
    assert payload["recent_failures"][0]["error_code"] == "TimeoutError"
    assert "device_token" not in str(payload)
