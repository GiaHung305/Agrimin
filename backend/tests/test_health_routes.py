import pytest

from app.api.routes import health


class _FailingDatabase:
    async def execute(self, _query):
        raise RuntimeError("postgresql://user:super-secret@private-host/database")


@pytest.mark.asyncio
async def test_health_response_does_not_expose_database_exception(monkeypatch):
    async def dependency_is_healthy():
        return True

    monkeypatch.setattr(health, "check_redis_connection", dependency_is_healthy)
    monkeypatch.setattr(health, "check_qdrant_connection", dependency_is_healthy)

    response = await health.health_check(db=_FailingDatabase())

    assert response == {
        "status": "degraded",
        "services": {"postgres": "down", "redis": "ok", "qdrant": "ok"},
    }
    assert "super-secret" not in str(response)
