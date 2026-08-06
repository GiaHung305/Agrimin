import json
import uuid
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from langfuse import propagate_attributes
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.db import get_db
from app.core.auth import get_current_user
from app.workflow.graph import build_graph
from app.repository.models import MemoryFact, Message, User, Conversation
from app.services.semantic_cache import get_cached_answer, store_answer
from app.core.langfuse_client import get_langfuse_handler
from app.core.security_checks import contains_prompt_injection

router = APIRouter(tags=["chat"])
limiter = Limiter(key_func=get_remote_address)


class ChatRequest(BaseModel):
    question: str = Field(..., max_length=1000, min_length=1)
    conversation_id: str | None = None


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
) -> dict:
    return {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "question": question,
        "context": {"known_facts": known_facts, "province": known_province, "conversation_history": conversation_history},
        "plan": None,
        "risk_level": "low",
        "retrieved_docs": [],
        "tool_results": {},
        "draft_answer": None,
        "citations": [],
        "confidence": 0.0,
        "reflection_notes": None,
        "retry_count": 0,
        "guardrail_status": None,
        "final_answer": None,
        "pending_action": None,
    }


async def _load_conversation_history(db: AsyncSession, conversation_id: str) -> list[dict]:
    result = await db.execute(
        select(Message.role, Message.content)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(8)
    )
    return [{"role": row.role, "content": row.content} for row in reversed(result.all())]


async def _prepare_chat(req: ChatRequest, db: AsyncSession, current_user: dict) -> PreparedChat:
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
    cached_response = None if conversation_history else await get_cached_answer(user_id, req.question, known_province, known_crop)
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
            user_id, conversation_id, req.question, known_facts, known_province, conversation_history
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
    if response_data["risk_level"] != "high" and response_data.get("guardrail_status") == "pass" and not response_data.get("pending_action"):
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


async def _buffered_response_events(response_data: dict):
    metadata = {key: value for key, value in response_data.items() if key != "answer"}
    yield _sse_event("meta", metadata, buffered=True)
    yield _sse_event("chunk", response_data["answer"])
    yield _sse_event("done")


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

    prepared = await _prepare_chat(req, db, current_user)
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
