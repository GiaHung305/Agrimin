import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.db import Base
from app.persistence import models  # noqa: F401


def test_operational_indexes_are_declared_in_orm_metadata():
    expected = {
        "ix_device_tokens_owner_active",
        "ix_farm_logs_owner_logged",
        "ix_farm_tasks_status_due",
        "ix_farm_tasks_user_due",
        "ix_messages_conversation_created",
        "ix_notifications_owner_created",
        "ix_pending_actions_owner_status",
        "ix_pending_actions_status_expiry",
    }
    actual = {
        index.name
        for table in Base.metadata.tables.values()
        for index in table.indexes
    }

    assert expected <= actual


def test_langgraph_checkpoint_tables_are_not_owned_by_application_metadata():
    external_tables = {
        "checkpoint_blobs",
        "checkpoint_migrations",
        "checkpoint_writes",
        "checkpoints",
    }

    assert external_tables.isdisjoint(Base.metadata.tables)
