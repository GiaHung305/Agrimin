"""Parallel, accumulating retrieval for the internal research workflow."""

import asyncio
import logging
from typing import Any

from app.retrieval.evidence import evidence_identity, normalize_evidence
from app.retrieval.hybrid_search import crop_keys_for_text, hybrid_search
from app.multimodal.contracts import build_visual_retrieval_query
from app.tools.mcp_weather_client import geocode_province_via_mcp, get_weather_via_mcp
from app.workflow.state import AgentState

logger = logging.getLogger(__name__)
MAX_RESEARCH_QUESTIONS = 4
MAX_ACCUMULATED_EVIDENCE = 12


def _expand_first_pass_query(question: str) -> str:
    """Add decision criteria to broad nutrition queries without adding an answer."""
    normalized = " ".join(question.casefold().split())
    if "quản lý dinh dưỡng" in normalized or "quan ly dinh duong" in normalized:
        return f"{question} bón phân cân đối theo nhu cầu cây và phân tích đất"
    return question


async def _retrieve_documents(question: str, need_rag: bool, top_k: int) -> list[dict]:
    return await hybrid_search(question, top_k=top_k) if need_rag else []


async def _retrieve_weather(need_weather: bool, province: str | None) -> dict | None:
    if not need_weather or not province:
        return None
    try:
        coords = await geocode_province_via_mcp(province)
        if not coords:
            return None
        lat, lon = coords
        return await get_weather_via_mcp(lat, lon)
    except Exception as exc:
        logger.warning(
            "Optional weather MCP lookup failed",
            extra={"error_type": type(exc).__name__},
        )
        return None


def _research_queries(state: AgentState) -> list[str]:
    plan = state.get("plan") or {}
    if not plan.get("need_rag", True):
        return []

    candidates = (
        state.get("missing_evidence", [])
        if state.get("retry_count", 0) > 0 and state.get("missing_evidence")
        else state.get("research_questions", [])
    )
    if not candidates:
        candidates = plan.get("research_questions") or [state["question"]]

    retry_count = state.get("retry_count", 0)
    retry_bases: dict[str, str] = {}
    if retry_count > 0:
        suffix = (
            "nhãn và hướng dẫn chính thức Việt Nam"
            if state.get("risk_level") == "high"
            else "tài liệu kỹ thuật khuyến nông Việt Nam"
        )
        expanded = []
        for candidate in candidates:
            base = " ".join(str(candidate).split()).strip()
            rewritten = f"{base} {suffix}" if base else ""
            if rewritten:
                retry_bases[rewritten] = base
                expanded.append(rewritten)
        candidates = expanded
    else:
        expanded = []
        for candidate in candidates:
            base = " ".join(str(candidate).split()).strip()
            rewritten = _expand_first_pass_query(base) if base else ""
            if rewritten:
                if rewritten != base:
                    retry_bases[rewritten] = base
                expanded.append(rewritten)
        candidates = expanded

    context = state.setdefault("context", {})
    context["research_retry_bases"] = retry_bases
    context.pop("vision_retrieval_query", None)
    context.pop("vision_retrieval_base_query", None)
    if state.get("retry_count", 0) == 0 and state.get("visual_observations"):
        base_query = str(state["question"])
        visual_query = build_visual_retrieval_query(
            base_query, state["visual_observations"]
        )
        if visual_query != base_query:
            visual_crops: set[str] = set()
            visual_labels: list[str] = []
            for observation in state["visual_observations"]:
                if (
                    observation.get("relevance") != "agriculture_plant"
                    or float(observation.get("confidence") or 0.0) < 0.60
                    or not observation.get("crop_candidate")
                ):
                    continue
                label = str(observation["crop_candidate"]).strip()
                visual_labels.append(label)
                visual_crops.update(crop_keys_for_text(label))
            stored_seasons = context.get("plot_seasons") or []
            stored_crops = {
                crop_key
                for season in stored_seasons
                for crop_key in crop_keys_for_text(str(season.get("crop") or ""))
            }
            crop_conflict = bool(
                visual_crops and stored_crops and visual_crops.isdisjoint(stored_crops)
            )
            context["visual_crop_context"] = {
                "visual_candidates": list(dict.fromkeys(visual_labels)),
                "stored_season_crops": list(dict.fromkeys(
                    str(season.get("crop"))
                    for season in stored_seasons
                    if season.get("crop")
                )),
                "conflict": crop_conflict,
            }
            candidates = (
                [visual_query]
                if crop_conflict
                else [visual_query, *candidates]
            )
            context["vision_retrieval_query"] = visual_query
            context["vision_retrieval_base_query"] = base_query
            if crop_conflict:
                # Coverage and retries must follow the user's image question,
                # not a planner question polluted by the stored crop.
                state["research_questions"] = [base_query]

    queries: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        query = " ".join(str(candidate).split()).strip()
        key = query.casefold()
        if not query or key in seen:
            continue
        seen.add(key)
        queries.append(query)
        if len(queries) == MAX_RESEARCH_QUESTIONS:
            break
    return queries


def _score(record: dict[str, Any], name: str) -> float:
    value = record.get(name)
    return float(value) if value is not None else 0.0


def _merge_evidence(existing: list[dict], incoming: list[dict]) -> list[dict]:
    merged = {evidence_identity(record): normalize_evidence(record) for record in existing}
    for candidate in incoming:
        normalized = normalize_evidence(candidate)
        identity = evidence_identity(normalized)
        current = merged.get(identity)
        if current is None:
            merged[identity] = normalized
            continue

        current["research_questions"] = list(dict.fromkeys([
            *current.get("research_questions", []),
            *normalized.get("research_questions", []),
        ]))
        for score_name in ("dense_score", "bm25_score", "fusion_score", "rerank_score"):
            if _score(normalized, score_name) > _score(current, score_name):
                current[score_name] = normalized.get(score_name)

    return sorted(
        merged.values(),
        key=lambda record: (
            _score(record, "rerank_score"),
            _score(record, "fusion_score"),
        ),
        reverse=True,
    )[:MAX_ACCUMULATED_EVIDENCE]


async def retrieve_node(state: AgentState) -> AgentState:
    plan = state.get("plan") or {}
    context = state.setdefault("context", {})
    queries = _research_queries(state)
    top_k = min(5 + (2 * state.get("retry_count", 0)), 9)

    should_fetch_weather = (
        plan.get("need_weather", False)
        and "weather" not in state.get("tool_results", {})
    )
    tasks = [
        _retrieve_documents(query, plan.get("need_rag", True), top_k)
        for query in queries
    ]
    gathered = await asyncio.gather(
        *tasks,
        _retrieve_weather(should_fetch_weather, context.get("province")),
    )
    query_results = gathered[:-1]
    weather = gathered[-1]

    incoming: list[dict] = []
    query_scores = dict(context.get("research_query_scores", {}))
    attempts = list(context.get("research_queries_attempted", []))
    for query, results in zip(queries, query_results):
        evidence_questions = [query]
        retry_base = context.get("research_retry_bases", {}).get(query)
        if retry_base:
            evidence_questions.insert(0, retry_base)
        if query == context.get("vision_retrieval_query"):
            evidence_questions.insert(0, context["vision_retrieval_base_query"])
        normalized_results = []
        for result in results:
            normalized = normalize_evidence(result)
            normalized["research_questions"] = list(dict.fromkeys([
                *normalized.get("research_questions", []),
                *evidence_questions,
            ]))
            normalized_results.append(normalized)
        incoming.extend(normalized_results)
        best_score = max(
            (_score(result, "rerank_score") for result in normalized_results),
            default=0.0,
        )
        query_scores[query] = max(float(query_scores.get(query, 0.0)), best_score)
        attempts.append({
            "query": query,
            "retry": state.get("retry_count", 0),
            "top_k": top_k,
            "results": len(normalized_results),
            "best_score": best_score,
        })

    state["retrieved_docs"] = _merge_evidence(
        state.get("retrieved_docs", []), incoming
    )
    rerank_scores = [
        _score(record, "rerank_score") for record in state["retrieved_docs"]
    ]
    context["max_relevance_score"] = max(rerank_scores, default=0.0)
    context["rerank_scores"] = rerank_scores
    context["research_query_scores"] = query_scores
    context["research_queries_attempted"] = attempts

    tool_results = dict(state.get("tool_results", {}))
    if weather:
        tool_results["weather"] = weather
    state["tool_results"] = tool_results
    return state
