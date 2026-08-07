from sqlalchemy.ext.asyncio import AsyncSession

from app.workflow.state import AgentState
from app.repository.models import Message


async def memory_write_node(state: AgentState, db: AsyncSession) -> AgentState:
    """
    Chỉ ghi vào Postgres khi Guardrail đã pass — không lưu câu trả lời bị chặn,
    tránh hệ thống coi các câu bị từ chối là "đã trả lời được".
    """
    # Defense in depth: even a future graph routing regression must never
    # persist an answer that did not pass the post-generation guardrail.
    if state.get("guardrail_status") != "pass":
        return state

    message = Message(
        conversation_id=state["conversation_id"],
        role="assistant",
        content=state["draft_answer"],
        risk_level=state["risk_level"],
        confidence_score=state["confidence"],
        guardrail_status=state["guardrail_status"],
    )
    db.add(message)
    await db.commit()

    state["final_answer"] = state["draft_answer"]
    return state
