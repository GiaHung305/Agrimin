import pytest

from app.workflow.nodes.memory_write import memory_write_node


class FailingDb:
    def add(self, value):
        raise AssertionError("blocked answer must not be added")

    async def commit(self):
        raise AssertionError("blocked answer must not be committed")


@pytest.mark.asyncio
async def test_blocked_answer_cannot_be_written_to_memory():
    state = {"guardrail_status": "block", "draft_answer": "unsafe"}
    result = await memory_write_node(state, FailingDb())
    assert result is state
    assert "final_answer" not in result
