import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi import HTTPException

from app.api.chat import ensure_user_and_conversation
from app.core import auth
from app.services.semantic_cache import _context_key


class ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


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


def test_semantic_cache_key_is_isolated_per_user():
    first_user_key = _context_key("user-a", "Dak Lak", "coffee")
    second_user_key = _context_key("user-b", "Dak Lak", "coffee")

    assert first_user_key != second_user_key


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
