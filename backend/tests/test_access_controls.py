import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi import HTTPException

from app.api.routes.chat import _load_plot_seasons, ensure_user_and_conversation
from app.core import auth
from app.services.semantic_cache import _context_key


class ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class RowsResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


@pytest.mark.asyncio
async def test_conversation_cannot_be_opened_by_another_user():
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[
            ScalarResult(SimpleNamespace(id="user-a")),
            ScalarResult(SimpleNamespace(user_id="user-b")),
        ]),
        commit=AsyncMock(),
    )

    with pytest.raises(HTTPException, match="Conversation not found") as error:
        await ensure_user_and_conversation(db, "user-a", "a@example.com", "conversation-b")

    assert error.value.status_code == 404
    ownership_query = str(db.execute.await_args_list[1].args[0])
    assert "conversations.id" in ownership_query
    assert "conversations.user_id" in ownership_query


def test_semantic_cache_key_is_isolated_per_user():
    first_user_key = _context_key(
        "user-a", "Dak Lak", "coffee", time_window="2026080710"
    )
    second_user_key = _context_key(
        "user-b", "Dak Lak", "coffee", time_window="2026080710"
    )

    assert first_user_key != second_user_key


def test_semantic_cache_key_changes_when_farm_profile_changes():
    first = _context_key(
        "user-1",
        "Lâm Đồng",
        "Bắp Cải",
        time_window="2026082010",
        farm_profile={
            "farm_profile": {"farming_style": "Normal"},
            "plot_seasons": [{"plot_id": "plot-1", "crop": "Bắp Cải"}],
        },
    )
    updated = _context_key(
        "user-1",
        "Lâm Đồng",
        "Bắp Cải",
        time_window="2026082010",
        farm_profile={
            "farm_profile": {"farming_style": "Normal"},
            "plot_seasons": [{"plot_id": "plot-1", "crop": "Cà chua"}],
        },
    )

    assert first != updated


@pytest.mark.asyncio
async def test_chat_loads_only_owned_active_plot_season_context():
    plot = SimpleNamespace(
        id="plot-1",
        name="Thửa A",
        area_ha=0.5,
        location_note="gần suối",
    )
    season = SimpleNamespace(
        id="season-1",
        crop="Bắp Cải",
        variety="F1",
        growth_stage="cây con",
        planted_on=None,
        expected_harvest_on=None,
        status="active",
    )
    db = SimpleNamespace(execute=AsyncMock(return_value=RowsResult([(plot, season)])))

    context = await _load_plot_seasons(db, "user-a")

    assert context[0]["plot_name"] == "Thửa A"
    assert context[0]["crop"] == "Bắp Cải"
    query = str(db.execute.await_args.args[0])
    assert "farm_plots.user_id" in query
    assert "crop_seasons.user_id" in query
    assert "farm_plots.status" in query
    assert "crop_seasons.status" in query


@pytest.mark.asyncio
async def test_document_management_requires_configured_admin_in_production(monkeypatch):
    monkeypatch.setattr(auth.settings, "environment", "production")
    monkeypatch.setattr(auth.settings, "admin_user_ids", "")
    monkeypatch.setattr(auth.settings, "admin_emails", "admin@example.com")

    with pytest.raises(HTTPException, match="administrator") as error:
        await auth.require_admin({"id": "user-a", "email": "user@example.com"})

    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_configured_admin_can_manage_documents(monkeypatch):
    monkeypatch.setattr(auth.settings, "environment", "production")
    monkeypatch.setattr(auth.settings, "admin_user_ids", "")
    monkeypatch.setattr(auth.settings, "admin_emails", "admin@example.com")
    current_user = {"id": "admin-id", "email": "ADMIN@example.com"}

    assert await auth.require_admin(current_user) == current_user
