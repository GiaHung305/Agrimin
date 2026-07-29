from functools import partial

from langgraph.graph import StateGraph, START, END
from sqlalchemy.ext.asyncio import AsyncSession

from app.workflow.state import AgentState
from app.workflow.nodes.planner import planner_node
from app.workflow.nodes.pre_guardrail import pre_guardrail_node
from app.workflow.nodes.retrieve import retrieve_node
from app.workflow.nodes.generate import generate_node
from app.workflow.nodes.reflection import reflection_node
from app.workflow.nodes.post_guardrail import post_guardrail_node
from app.workflow.nodes.fallback import fallback_node
from app.workflow.nodes.memory_write import memory_write_node
from app.workflow.nodes.memory_extract import memory_extract_node


def build_graph(db: AsyncSession):
    workflow = StateGraph(AgentState)

    workflow.add_node("planner", planner_node)
    workflow.add_node("pre_guardrail", pre_guardrail_node)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("generate", generate_node)
    workflow.add_node("reflection", reflection_node)
    workflow.add_node("post_guardrail", post_guardrail_node)
    workflow.add_node("fallback", fallback_node)
    workflow.add_node("memory_write", partial(memory_write_node, db=db))
    workflow.add_node("memory_extract", partial(memory_extract_node, db=db))

    workflow.add_edge(START, "planner")
    workflow.add_edge("planner", "pre_guardrail")
    workflow.add_edge("pre_guardrail", "retrieve")
    workflow.add_edge("retrieve", "generate")
    workflow.add_edge("generate", "reflection")

    workflow.add_conditional_edges(
        "reflection",
        lambda s: "post_guardrail" if s["reflection_notes"] == "sufficient" or s["retry_count"] >= 2 else "retrieve",
        {"post_guardrail": "post_guardrail", "retrieve": "retrieve"},
    )

    workflow.add_conditional_edges(
        "post_guardrail",
        lambda s: "pass" if s["guardrail_status"] == "pass" else "block",
        {"pass": "memory_write", "block": "fallback"},
    )

    workflow.add_edge("memory_write", "memory_extract")
    workflow.add_edge("memory_extract", END)
    workflow.add_edge("fallback", END)

    return workflow.compile()