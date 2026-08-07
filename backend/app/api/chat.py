import asyncio
import json
import logging
import uuid
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from langfuse import propagate_attributes
from slowapi import Limiter
from slowapi.util import get_remote_address
from google.genai.errors import ServerError

from app.core.db import get_db
from app.core.auth import get_current_user
from app.workflow.graph import build_graph
from app.repository.models import MemoryFact, Message, User, Conversation
from app.services.semantic_cache import (
    get_cached_answer,
    is_realtime_sensitive_question,
    store_answer,
)
from app.services.model_gateway import ModelProviderUnavailable
from app.core.model_registry import runtime_versions
from app.core.langfuse_client import get_langfuse_handler
from app.core.security_checks import contains_prompt_injection
from app.core.config import settings
from app.multimodal.contracts import (
    SCHEMA_VERSION,
    VisualAnalysisResult,
    validate_analysis_image_scope,
)
from app.multimodal.image_validation import (
    ImageValidationError,
    validate_chat_image_payload,
)
from app.multimodal.vision_analyzer import (
    VisionAnalyzerUnavailable,
    analyze_validated_images,
)

router = APIRouter(tags=["chat"])
limiter = Limiter(key_func=get_remote_address)
logger = logging.getLogger(__name__)


class ChatImageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mime_type: str = Field(..., min_length=1, max_length=50)
    data_base64: str = Field(..., min_length=16, max_length=6_000_000)


class ChatRequest(BaseModel):
    question: str = Field(..., max_length=1000, min_length=1)
    conversation_id: str | None = None
    deep_research: bool = False
    images: list[ChatImageInput] = Field(default_factory=list, max_length=2)


@dataclass
class PreparedChat:
    user_id: str
    conversation_id: str
    known_facts: list[dict]
    known_province: str | None
    known_crop: str | None
    conversation_history: list[dict]
    initial_state: dict
    cached_response: dict | None


@dataclass
class PreparedVisualInput:
    image_observations: list[dict]
    visual_observations: list[dict]
    vision_error: str | None


async def ensure_user_and_conversation(db: AsyncSession, user_id: str, email: str, conversation_id: str | None) -> str:
    """
    Tự động tạo user (nếu chưa có) và conversation (nếu chưa có hoặc chưa hợp lệ).
    Cần thiết vì user đăng ký qua Supabase Auth không tự động có trong Postgres.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        user = User(id=user_id, name=email or "User")
        db.add(user)
        await db.flush()

    if conversation_id:
        result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
        conv = result.scalar_one_or_none()
        if conv:
            if str(conv.user_id) == str(user_id):
                await db.commit()
                return conversation_id
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    new_conv_id = str(uuid.uuid4())
    conv = Conversation(id=new_conv_id, user_id=user_id, title="Cuộc trò chuyện mới")
    db.add(conv)
    await db.commit()
    return new_conv_id


async def _load_known_facts(db: AsyncSession, user_id: str):
    facts_result = await db.execute(
        select(MemoryFact.fact_text).where(MemoryFact.user_id == user_id)
    )
    known_facts_raw = [row[0] for row in facts_result.all()]

    known_province = None
    known_crop = None
    known_facts_display = []
    for raw in known_facts_raw:
        try:
            parsed = json.loads(raw)
            known_facts_display.append(parsed)
            if parsed.get("province"):
                known_province = parsed["province"]
            if parsed.get("crop"):
                known_crop = parsed["crop"]
        except (json.JSONDecodeError, TypeError):
            continue

    return known_facts_display, known_province, known_crop


def _new_agent_state(
    user_id: str,
    conversation_id: str,
    question: str,
    known_facts: list[dict],
    known_province: str | None,
    conversation_history: list[dict],
    deep_research: bool,
    image_observations: list[dict] | None = None,
    visual_observations: list[dict] | None = None,
    vision_error: str | None = None,
) -> dict:
    return {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "question": question,
        "image_observations": image_observations or [],
        "visual_observations": visual_observations or [],
        "context": {
            "known_facts": known_facts,
            "province": known_province,
            "conversation_history": conversation_history,
            "request_deep_research": deep_research,
            "vision_error": vision_error,
        },
        "plan": None,
        "risk_level": "low",
        "retrieved_docs": [],
        "tool_results": {},
        "draft_answer": None,
        "citations": [],
        "confidence": 0.0,
        "reflection_notes": None,
        "retry_count": 0,
        "research_questions": [],
        "research_coverage": [],
        "missing_evidence": [],
        "evidence_conflicts": [],
        "research_stop_reason": None,
        "guardrail_status": None,
        "final_answer": None,
        "pending_action": None,
        "research_sources": [],
    }


async def _load_conversation_history(db: AsyncSession, conversation_id: str) -> list[dict]:
    result = await db.execute(
        select(Message.role, Message.content)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(8)
    )
    return [{"role": row.role, "content": row.content} for row in reversed(result.all())]


def _should_bypass_cache(req: ChatRequest, conversation_history: list[dict]) -> bool:
    return (
        bool(conversation_history)
        or req.deep_research
        or bool(req.images)
        or is_realtime_sensitive_question(req.question)
    )


async def _prepare_chat(
    req: ChatRequest,
    db: AsyncSession,
    current_user: dict,
    image_observations: list[dict],
    visual_observations: list[dict],
    vision_error: str | None,
) -> PreparedChat:
    """Create the session, memory, cache and initial state for the chat flow."""
    user_id = current_user["id"]
    conversation_id = await ensure_user_and_conversation(
        db, user_id, current_user["email"], req.conversation_id
    )
    known_facts, known_province, known_crop = await _load_known_facts(db, user_id)
    conversation_history = await _load_conversation_history(db, conversation_id)
    db.add(Message(conversation_id=conversation_id, role="user", content=req.question))
    await db.commit()
    # A cached answer is valid only for a new turn. Follow-up questions depend
    # on previous conversation context and must run through the graph.
    bypass_cache = _should_bypass_cache(req, conversation_history)
    cached_response = None if bypass_cache else await get_cached_answer(
        user_id, req.question, known_province, known_crop
    )
    if cached_response:
        cached_response["conversation_id"] = conversation_id

    return PreparedChat(
        user_id=user_id,
        conversation_id=conversation_id,
        known_facts=known_facts,
        known_province=known_province,
        known_crop=known_crop,
        conversation_history=conversation_history,
        initial_state=_new_agent_state(
            user_id,
            conversation_id,
            req.question,
            known_facts,
            known_province,
            conversation_history,
            req.deep_research,
            image_observations,
            visual_observations,
            vision_error,
        ),
        cached_response=cached_response,
    )


def _build_trace(result: dict) -> dict:
    context = result.get("context", {})
    plan = result.get("plan") or {}
    retrieved_docs = result.get("retrieved_docs", [])
    return {
        "planner": {
            "risk_level": result.get("risk_level"),
            "need_rag": plan.get("need_rag"),
            "need_weather": plan.get("need_weather"),
            "deep_research": plan.get("need_deep_research", False),
            "need_vision": plan.get("need_vision", False),
        },
        "retriever": {
            "docs_found": len(retrieved_docs),
            "top_source": retrieved_docs[0]["source"] if retrieved_docs else None,
            "max_relevance_score": context.get("max_relevance_score"),
        },
        "weather": {
            "used": "weather" in result.get("tool_results", {}),
            "province": context.get("province"),
        },
        "reflection": {
            "notes": result.get("reflection_notes"),
            "retry_count": result.get("retry_count", 0),
        },
        "guardrail": {
            "status": result.get("guardrail_status"),
            "confidence": result.get("confidence"),
        },
        "research": {
            "used": context.get("deep_research_used", False),
            "sources_found": context.get("research_source_count", 0),
            "error": context.get("research_error"),
            "questions": result.get("research_questions", []),
            "coverage": result.get("research_coverage", []),
            "missing_evidence": result.get("missing_evidence", []),
            "contradictions": result.get("evidence_conflicts", []),
            "stop_reason": result.get("research_stop_reason"),
            "retry_count": result.get("retry_count", 0),
        },
        "vision": {
            "mode": (
                "typed_observations"
                if result.get("visual_observations")
                else "validation_only"
            ),
            "observations": result.get("image_observations", []),
            "visual_observations": result.get("visual_observations", []),
            "error": context.get("vision_error"),
            "retrieval_query": context.get("vision_retrieval_query"),
            "stop_reason": context.get("vision_stop"),
        },
        "versions": runtime_versions(),
    }


def _response_from_result(result: dict, conversation_id: str) -> dict:
    return {
        "answer": result.get("final_answer") or result.get("draft_answer"),
        "citations": result.get("citations", []),
        "confidence": result.get("confidence", 0.0),
        "risk_level": result.get("risk_level", "low"),
        "guardrail_status": result.get("guardrail_status"),
        "plan": result.get("plan"),
        "trace": _build_trace(result),
        "conversation_id": conversation_id,
        "pending_action": result.get("pending_action"),
    }


async def _cache_response_if_safe(req: ChatRequest, prepared: PreparedChat, response_data: dict):
    if (
        not req.images
        and not (response_data.get("plan") or {}).get("need_deep_research", False)
        and not (response_data.get("plan") or {}).get("need_weather", False)
        and response_data["risk_level"] != "high"
        and response_data.get("guardrail_status") == "pass"
        and not response_data.get("pending_action")
    ):
        await store_answer(
            prepared.user_id,
            req.question,
            prepared.known_province,
            prepared.known_crop,
            response_data,
        )


async def _record_cached_answer(db: AsyncSession, conversation_id: str, response_data: dict) -> None:
    """Keep database history complete when a semantic-cache hit skips the graph."""
    db.add(Message(
        conversation_id=conversation_id,
        role="assistant",
        content=response_data["answer"],
        risk_level=response_data.get("risk_level"),
        confidence_score=response_data.get("confidence"),
        guardrail_status=response_data.get("guardrail_status"),
    ))
    await db.commit()


def _sse_event(event_type: str, payload: dict | str | None = None, **extra) -> str:
    event = {"type": event_type, **extra}
    if payload is not None:
        event["payload"] = payload
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _blocked_response(conversation_id: str | None) -> dict:
    return {
        "answer": "Câu hỏi của bạn chứa nội dung không hợp lệ, vui lòng đặt câu hỏi khác về nông nghiệp.",
        "citations": [],
        "confidence": 0.0,
        "risk_level": "low",
        "guardrail_status": "block",
        "plan": None,
        "conversation_id": conversation_id,
    }


def _provider_unavailable_response(conversation_id: str) -> dict:
    return {
        "answer": "Dịch vụ AI đang tạm thời quá tải. Vui lòng thử lại sau ít phút.",
        "citations": [],
        "confidence": 0.0,
        "risk_level": "low",
        "guardrail_status": "block",
        "plan": None,
        "trace": {"provider": {"status": "temporarily_unavailable"}},
        "conversation_id": conversation_id,
        "pending_action": None,
    }


async def _buffered_response_events(response_data: dict):
    metadata = {key: value for key, value in response_data.items() if key != "answer"}
    yield _sse_event("meta", metadata, buffered=True)
    yield _sse_event("chunk", response_data["answer"])
    yield _sse_event("done")


async def _prepare_visual_input(images: list[ChatImageInput]) -> PreparedVisualInput:
    """Validate raw images and discard their bytes before graph state is built."""
    validated_images = await asyncio.gather(*(
        asyncio.to_thread(
            validate_chat_image_payload, image.data_base64, image.mime_type
        )
        for image in images
    ))
    image_observations = [item.observation for item in validated_images]
    usable_images = [
        item for item in validated_images if item.observation["usable_for_vision"]
    ]

    if not usable_images:
        validated_images.clear()
        return PreparedVisualInput(image_observations, [], None)
    if not settings.vision_analysis_enabled:
        validated_images.clear()
        return PreparedVisualInput(image_observations, [], "disabled")

    try:
        raw_result = await asyncio.wait_for(
            analyze_validated_images(usable_images),
            timeout=settings.vision_request_timeout_seconds,
        )
        result = VisualAnalysisResult.model_validate(raw_result)
        if settings.vision_observation_schema_version != SCHEMA_VERSION:
            raise ValueError("configured vision schema version is unsupported")
        validate_analysis_image_scope(
            result,
            {item.observation["image_id"] for item in usable_images},
        )
        serialized = result.model_dump(mode="json")
        if contains_prompt_injection(json.dumps(serialized, ensure_ascii=False)):
            logger.warning("Vision analyzer output failed prompt-injection screening")
            return PreparedVisualInput(image_observations, [], "unsafe_output")
        return PreparedVisualInput(
            image_observations,
            [item.model_dump(mode="json") for item in result.observations],
            None,
        )
    except TimeoutError:
        logger.warning("Vision analyzer timed out")
        return PreparedVisualInput(image_observations, [], "timeout")
    except VisionAnalyzerUnavailable:
        logger.warning("Vision analyzer is unavailable")
        return PreparedVisualInput(image_observations, [], "unavailable")
    except (ValidationError, ValueError):
        logger.warning("Vision analyzer returned invalid structured output", exc_info=True)
        return PreparedVisualInput(image_observations, [], "invalid_output")
    except Exception:
        logger.warning("Optional vision analyzer failed", exc_info=True)
        return PreparedVisualInput(image_observations, [], "unavailable")
    finally:
        # The graph, cache, trace and checkpointer must never receive raw bytes.
        usable_images.clear()
        validated_images.clear()


@router.post("/chat/stream")
@limiter.limit("10/minute")
async def chat_stream(
    request: Request,
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Serve the Flutter UI's SSE contract through the canonical graph flow."""

    if contains_prompt_injection(req.question):
        return StreamingResponse(
            _buffered_response_events(_blocked_response(req.conversation_id)),
            media_type="text/event-stream",
        )

    try:
        visual_input = await _prepare_visual_input(req.images)
    except ImageValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    prepared = await _prepare_chat(
        req,
        db,
        current_user,
        visual_input.image_observations,
        visual_input.visual_observations,
        visual_input.vision_error,
    )
    if prepared.cached_response:
        await _record_cached_answer(db, prepared.conversation_id, prepared.cached_response)
        return StreamingResponse(
            _buffered_response_events(prepared.cached_response),
            media_type="text/event-stream",
        )

    async def event_generator():
        graph = build_graph(db)
        graph_config = {
            "callbacks": [get_langfuse_handler()],
            "configurable": {"thread_id": prepared.conversation_id},
        }
        final_state = None
        streamed_answer = ""

        try:
            with propagate_attributes(
                trace_name="agrimind-chat",
                session_id=prepared.conversation_id,
                user_id=prepared.user_id,
            ):
                async for mode, payload in graph.astream(
                    prepared.initial_state,
                    config=graph_config,
                    stream_mode=["custom", "values"],
                ):
                    if mode == "custom" and payload.get("type") == "token":
                        text = payload["text"]
                        streamed_answer += text
                        yield _sse_event("chunk", text)
                    elif mode == "values":
                        final_state = payload
        except (ServerError, ModelProviderUnavailable):
            logger.warning("Model provider temporarily unavailable during chat")
            response_data = _provider_unavailable_response(prepared.conversation_id)
            fallback_text = response_data["answer"]
            if streamed_answer:
                fallback_text = "\n\n" + fallback_text
            yield _sse_event("chunk", fallback_text)
            metadata = {key: value for key, value in response_data.items() if key != "answer"}
            yield _sse_event("meta", metadata, buffered=bool(streamed_answer))
            yield _sse_event("done")
            return

        if final_state is None:
            raise RuntimeError("Chat graph completed without a final state")

        response_data = _response_from_result(final_state, prepared.conversation_id)
        final_answer = response_data["answer"] or ""
        if final_answer.startswith(streamed_answer):
            remaining_text = final_answer[len(streamed_answer):]
            if remaining_text:
                yield _sse_event("chunk", remaining_text)
        elif not streamed_answer:
            yield _sse_event("chunk", final_answer)
        else:
            raise RuntimeError("Final answer diverged from streamed content")

        await _cache_response_if_safe(req, prepared, response_data)
        metadata = {key: value for key, value in response_data.items() if key != "answer"}
        yield _sse_event("meta", metadata, buffered=False)
        yield _sse_event("done")

    return StreamingResponse(event_generator(), media_type="text/event-stream")
