"""Run the versioned golden dataset through the production SSE chat route."""

import asyncio
import json
import os
import sys
from typing import Any

import httpx
from google import genai
from sqlalchemy import select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import settings
from app.core.model_registry import ModelRole, model_name, runtime_fingerprint
from app.core.db import AsyncSessionLocal
from app.repository.models import EvalRun, GoldenDataset


judge_client = genai.Client(api_key=settings.google_api_key)


def parse_sse_response(raw: str) -> dict[str, Any]:
    """Parse the canonical ``data: JSON`` SSE contract by event delimiter."""
    answer_parts: list[str] = []
    metadata: dict[str, Any] = {}
    normalized = raw.replace("\r\n", "\n")
    for block in normalized.split("\n\n"):
        data_lines = [line[5:].lstrip() for line in block.splitlines() if line.startswith("data:")]
        if not data_lines:
            continue
        event = json.loads("\n".join(data_lines))
        if event.get("type") == "chunk":
            answer_parts.append(str(event.get("payload") or ""))
        elif event.get("type") == "meta":
            metadata.update(event.get("payload") or {})
    return {"answer": "".join(answer_parts), **metadata}


async def get_supabase_token(client: httpx.AsyncClient) -> str:
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY are required")
    if not settings.eval_user_email or not settings.eval_user_password:
        raise RuntimeError("EVAL_USER_EMAIL and EVAL_USER_PASSWORD are required")
    response = await client.post(
        f"{settings.supabase_url.rstrip('/')}/auth/v1/token?grant_type=password",
        headers={"apikey": settings.supabase_publishable_key, "Content-Type": "application/json"},
        json={"email": settings.eval_user_email, "password": settings.eval_user_password},
    )
    response.raise_for_status()
    token = response.json().get("access_token")
    if not token:
        raise RuntimeError("Supabase authentication returned no access token")
    return token


async def invoke_production_chat(
    client: httpx.AsyncClient, token: str, question: str
) -> dict[str, Any]:
    response = await client.post(
        settings.eval_api_url,
        headers={"Authorization": f"Bearer {token}", "Accept": "text/event-stream"},
        json={"question": question},
    )
    response.raise_for_status()
    return parse_sse_response(response.text)


async def llm_judge(expected: str, actual: str) -> float:
    prompt = f"""Expected answer: {expected}
Actual answer: {actual}

Score whether the actual answer contains the expected core facts. Return only a number from 0 to 1."""
    response = await judge_client.aio.models.generate_content(
        model=settings.eval_judge_model,
        contents=prompt,
    )
    try:
        return min(1.0, max(0.0, float((response.text or "").strip())))
    except ValueError:
        return 0.0


def citation_matches(expected: str | None, citations: list[Any]) -> bool:
    if not expected:
        return False
    needle = expected.casefold()
    for citation in citations:
        if isinstance(citation, str) and needle in citation.casefold():
            return True
        if isinstance(citation, dict):
            searchable = " ".join(
                str(citation.get(key) or "")
                for key in ("title", "source", "version", "url", "document_id", "chunk_id")
            )
            if needle in searchable.casefold():
                return True
    return False


async def run_eval() -> None:
    async with httpx.AsyncClient(timeout=90.0) as client_http:
        token = await get_supabase_token(client_http)

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(GoldenDataset).where(
                    GoldenDataset.dataset_version == settings.eval_dataset_version
                )
            )
            questions = result.scalars().all()
            if not questions:
                raise RuntimeError(
                    f"No golden dataset rows for version {settings.eval_dataset_version!r}"
                )

            correct = citation_matches_count = citation_total = blocked_correct = blocked_total = 0
            for item in questions:
                data = await invoke_production_chat(client_http, token, item.question)
                is_guardrail_test = item.expected_answer.startswith("BLOCKED")
                if is_guardrail_test:
                    blocked_total += 1
                    blocked_correct += data.get("guardrail_status") == "block"
                else:
                    correct += await llm_judge(item.expected_answer, data.get("answer", "")) > 0.3
                    if item.expected_citation:
                        citation_total += 1
                        citation_matches_count += citation_matches(
                            item.expected_citation, data.get("citations", [])
                        )
                await asyncio.sleep(settings.eval_request_delay_seconds)

            normal_total = len(questions) - blocked_total
            accuracy = correct / normal_total if normal_total else 0.0
            citation_score = citation_matches_count / citation_total if citation_total else 1.0
            guardrail_accuracy = blocked_correct / blocked_total if blocked_total else 1.0
            passed = accuracy >= 0.7 and guardrail_accuracy == 1.0
            db.add(
                EvalRun(
                    model_version=(
                        f"runtime={runtime_fingerprint()};"
                        f"generate={model_name(ModelRole.GENERATION)};"
                        f"judge={model_name(ModelRole.JUDGE)}"
                    ),
                    dataset_version=settings.eval_dataset_version,
                    accuracy=accuracy,
                    citation_score=citation_score,
                    hallucination_rate=1 - guardrail_accuracy,
                    passed=passed,
                )
            )
            await db.commit()

    print(f"dataset={settings.eval_dataset_version}")
    print(f"accuracy={accuracy:.2%}")
    print(f"citation_match={citation_score:.2%}")
    print(f"guardrail_accuracy={guardrail_accuracy:.2%}")
    print(f"passed={passed}")


if __name__ == "__main__":
    asyncio.run(run_eval())
