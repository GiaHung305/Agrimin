from app.workflow.state import AgentState


async def pre_guardrail_node(state: AgentState) -> AgentState:
    """
    Gắn cờ yêu cầu nghiêm ngặt nếu risk_level=high.
    Việc chặn thật sự xảy ra ở post_guardrail, sau khi đã có retrieved_docs.
    """
    if state["risk_level"] == "high":
        state["context"]["require_citation"] = True
    return state