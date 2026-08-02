import json
import uuid

from fastapi import APIRouter, Depends, Request
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
from app.repository.models import MemoryFact, User, Conversation, Message
from app.services.semantic_cache import get_cached_answer, store_answer
from app.core.langfuse_client import get_langfuse_handler
from app.workflow.nodes.planner import planner_node
from app.workflow.nodes.pre_guardrail import pre_guardrail_node
from app.workflow.nodes.retrieve import retrieve_node
from app.workflow.nodes.generate import client as gemini_client, MODEL_STRONG

router = APIRouter(tags=["chat"])
limiter = Limiter(key_func=get_remote_address)


class ChatRequest(BaseModel):
    question: str = Field(..., max_length=1000, min_length=1)
    conversation_id: str | None = None


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
            await db.commit()
            return conversation_id

    new_conv_id = conversation_id or str(uuid.uuid4())
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


async def _run_chat_pipeline(req: ChatRequest, db: AsyncSession, current_user: dict) -> dict:
    user_id = current_user["id"]
    conversation_id = await ensure_user_and_conversation(db, user_id, current_user["email"], req.conversation_id)

    known_facts_display, known_province, known_crop = await _load_known_facts(db, user_id)

    cached = await get_cached_answer(req.question, known_province, known_crop)
    if cached:
        cached["conversation_id"] = conversation_id
        return cached

    initial_state = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "question": req.question,
        "context": {"known_facts": known_facts_display, "province": known_province},
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
    }

    graph = build_graph(db)

    with propagate_attributes(
        trace_name="agrimind-chat",
        session_id=conversation_id,
        user_id=user_id,
    ):
        langfuse_handler = get_langfuse_handler()
        result = await graph.ainvoke(
            initial_state,
            config={"callbacks": [langfuse_handler]},
        )

    answer = result.get("final_answer") or result.get("draft_answer")

    trace = {
        "planner": {
            "risk_level": result["risk_level"],
            "need_rag": result["plan"].get("need_rag") if result.get("plan") else None,
            "need_weather": result["plan"].get("need_weather") if result.get("plan") else None,
        },
        "retriever": {
            "docs_found": len(result.get("retrieved_docs", [])),
            "top_source": result["retrieved_docs"][0]["source"] if result.get("retrieved_docs") else None,
            "max_relevance_score": result["context"].get("max_relevance_score"),
        },
        "weather": {
            "used": "weather" in result.get("tool_results", {}),
            "province": result["context"].get("province"),
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

    response_data = {
        "answer": answer,
        "citations": result["citations"],
        "confidence": result["confidence"],
        "risk_level": result["risk_level"],
        "guardrail_status": result.get("guardrail_status"),
        "plan": result["plan"],
        "trace": trace,
        "conversation_id": conversation_id,
    }

    if result["risk_level"] != "high" and result.get("guardrail_status") == "pass":
        await store_answer(req.question, known_province, known_crop, response_data)

    return response_data


@router.post("/chat")
@limiter.limit("10/minute")
async def chat(
    request: Request,
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return await _run_chat_pipeline(req, db, current_user)


@router.post("/chat/stream")
@limiter.limit("10/minute")
async def chat_stream(
    request: Request,
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Streaming THẬT từ Gemini — nhưng chỉ cho risk_level != "high".
    Guardrail chỉ có khả năng BLOCK khi risk_level == "high" (câu hỏi
    liều lượng/hóa chất). Với risk thấp/trung bình, Guardrail không bao
    giờ chặn (chỉ thêm disclaimer), nên an toàn để hiển thị token ngay
    khi Gemini sinh ra. Với risk cao, vẫn dùng pipeline đầy đủ (không
    stream) — an toàn quan trọng hơn UX mượt trong trường hợp này.
    """
    user_id = current_user["id"]
    conversation_id = await ensure_user_and_conversation(db, user_id, current_user["email"], req.conversation_id)
    known_facts_display, known_province, known_crop = await _load_known_facts(db, user_id)

    async def event_generator():
        state = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "question": req.question,
            "context": {"known_facts": known_facts_display, "province": known_province},
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
        }

        state = await planner_node(state)
        state = await pre_guardrail_node(state)
        state = await retrieve_node(state)

        if state["risk_level"] == "high":
            result_data = await _run_chat_pipeline(req, db, current_user)
            meta = {k: v for k, v in result_data.items() if k != "answer"}
            yield f"data: {json.dumps({'type': 'meta', 'payload': meta, 'buffered': True}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'chunk', 'payload': result_data['answer']}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
            return

        docs_text = "\n".join([d["content"] for d in state["retrieved_docs"]])
        facts_text = "\n".join(str(f) for f in known_facts_display) if known_facts_display else "Chưa có thông tin."
        weather_text = "Không có dữ liệu thời tiết."
        if "weather" in state.get("tool_results", {}):
            weather_text = str(state["tool_results"]["weather"].get("forecast", ""))

        prompt = f"""Bạn là chuyên gia nông nghiệp Việt Nam. Trả lời câu hỏi dựa trên tài liệu sau:

Tài liệu:
{docs_text}

Thông tin đã biết về người dùng:
{facts_text}

Dữ liệu thời tiết 3 ngày tới:
{weather_text}

Câu hỏi: {req.question}

Trả lời ngắn gọn, chính xác, có xét đến thông tin về người dùng và thời tiết nếu liên quan."""

        citations = [d["source"] for d in state["retrieved_docs"]]
        meta = {
            "citations": citations,
            "risk_level": state["risk_level"],
            "conversation_id": conversation_id,
            "plan": state["plan"],
        }
        yield f"data: {json.dumps({'type': 'meta', 'payload': meta, 'buffered': False}, ensure_ascii=False)}\n\n"

        accumulated_text = ""
        async for chunk in await gemini_client.aio.models.generate_content_stream(
            model=MODEL_STRONG, contents=prompt
        ):
            if chunk.text:
                accumulated_text += chunk.text
                yield f"data: {json.dumps({'type': 'chunk', 'payload': chunk.text}, ensure_ascii=False)}\n\n"

        confidence = 0.8
        if confidence < 0.70:
            disclaimer = "\n\n(Lưu ý: tôi chưa hoàn toàn chắc chắn, bạn nên hỏi thêm cán bộ khuyến nông.)"
            accumulated_text += disclaimer
            yield f"data: {json.dumps({'type': 'chunk', 'payload': disclaimer}, ensure_ascii=False)}\n\n"

        response_data = {
            "answer": accumulated_text,
            "citations": citations,
            "confidence": confidence,
            "risk_level": state["risk_level"],
            "guardrail_status": "pass",
            "plan": state["plan"],
            "conversation_id": conversation_id,
        }
        message = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=accumulated_text,
            risk_level=state["risk_level"],
            confidence_score=confidence,
            guardrail_status="pass",
        )
        db.add(message)
        await db.commit()
        await store_answer(req.question, known_province, known_crop, response_data)

        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")