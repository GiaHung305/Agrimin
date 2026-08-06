import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.core import checkpointer
from app.workflow import graph


class FakeSaver:
    def __init__(self):
        self.setup_called = False

    async def setup(self):
        self.setup_called = True


class FakeSaverContext:
    def __init__(self, saver):
        self.saver = saver
        self.exit_args = None

    async def __aenter__(self):
        return self.saver

    async def __aexit__(self, *args):
        self.exit_args = args


@pytest.mark.asyncio
async def test_checkpointer_initialises_once_and_closes(monkeypatch):
    saver = FakeSaver()
    context = FakeSaverContext(saver)

    class FakeAsyncPostgresSaver:
        @staticmethod
        def from_conn_string(connection_string):
            assert connection_string.startswith("postgresql://")
            return context

    monkeypatch.setattr(checkpointer, "AsyncPostgresSaver", FakeAsyncPostgresSaver)
    await checkpointer.close_checkpointer()

    assert await checkpointer.init_checkpointer() is saver
    assert saver.setup_called
    assert await checkpointer.init_checkpointer() is saver
    assert checkpointer.get_checkpointer() is saver

    await checkpointer.close_checkpointer()
    assert context.exit_args == (None, None, None)
    with pytest.raises(RuntimeError, match="has not been initialized"):
        checkpointer.get_checkpointer()


def test_build_graph_uses_initialised_postgres_checkpointer(monkeypatch):
    saver = InMemorySaver()
    monkeypatch.setattr(graph, "get_checkpointer", lambda: saver)

    compiled_graph = graph.build_graph(db=object())

    assert compiled_graph.checkpointer is saver
