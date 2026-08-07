from functools import partial

from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.checkpointer import get_checkpointer
from app.workflow.nodes.action_proposal import action_proposal_node
from app.workflow.nodes.deep_research import deep_research_node
from app.workflow.nodes.fallback import fallback_node
from app.workflow.nodes.generate import generate_node
from app.workflow.nodes.image_quality_guard import (
    image_quality_guard_node,
    route_after_image_quality,
)
from app.workflow.nodes.memory_extract import memory_extract_node
from app.workflow.nodes.memory_write import memory_write_node
from app.workflow.nodes.planner import planner_node
from app.workflow.nodes.post_guardrail import post_guardrail_node
from app.workflow.nodes.pre_guardrail import pre_guardrail_node
from app.workflow.nodes.reflection import reflection_node
from app.workflow.nodes.research_analysis import research_analysis_node
from app.workflow.nodes.retrieve import retrieve_node
from app.workflow.state import AgentState


def route_after_research_analysis(state: AgentState) -> str:
    if state.get("research_stop_reason") in {
        "retry_missing_evidence",
        "retry_contradiction",
    }:
        return "retrieve"
    if (state.get("plan") or {}).get("need_deep_research", False):
        return "deep_research"
    return "generate"


def route_after_deep_research(state: AgentState) -> str:
    return (
        "reflection"
        if state.get("context", {}).get("deep_research_used", False)
        else "generate"
    )


def route_after_reflection(state: AgentState) -> str:
    return "post_guardrail"


def build_graph(db: AsyncSession):
    workflow = StateGraph(AgentState)

    workflow.add_node("planner", planner_node)
    workflow.add_node("image_quality_guard", image_quality_guard_node)
    workflow.add_node("pre_guardrail", pre_guardrail_node)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("research_analysis", research_analysis_node)
    workflow.add_node("deep_research", deep_research_node)
    workflow.add_node("generate", generate_node)
    workflow.add_node("reflection", reflection_node)
    workflow.add_node("post_guardrail", post_guardrail_node)
    workflow.add_node("fallback", fallback_node)
    workflow.add_node("memory_write", partial(memory_write_node, db=db))
    workflow.add_node("memory_extract", partial(memory_extract_node, db=db))
    workflow.add_node("action_proposal", partial(action_proposal_node, db=db))

    workflow.add_edge(START, "image_quality_guard")
    workflow.add_conditional_edges(
        "image_quality_guard",
        route_after_image_quality,
        {"continue": "planner", "stop": END},
    )
    workflow.add_edge("planner", "pre_guardrail")
    workflow.add_edge("pre_guardrail", "retrieve")
    workflow.add_edge("retrieve", "research_analysis")
    workflow.add_conditional_edges(
        "research_analysis",
        route_after_research_analysis,
        {
            "retrieve": "retrieve",
            "deep_research": "deep_research",
            "generate": "generate",
        },
    )
    # A provider outage degrades safely to the internal RAG generation path.
    workflow.add_conditional_edges(
        "deep_research",
        route_after_deep_research,
        {"reflection": "reflection", "generate": "generate"},
    )
    workflow.add_edge("generate", "reflection")
    workflow.add_conditional_edges(
        "reflection",
        route_after_reflection,
        {"post_guardrail": "post_guardrail"},
    )

    workflow.add_conditional_edges(
        "post_guardrail",
        lambda state: "pass" if state["guardrail_status"] == "pass" else "block",
        {"pass": "memory_write", "block": "fallback"},
    )

    workflow.add_edge("memory_write", "action_proposal")
    workflow.add_edge("action_proposal", "memory_extract")
    workflow.add_edge("memory_extract", END)
    workflow.add_edge("fallback", END)

    return workflow.compile(checkpointer=get_checkpointer())
