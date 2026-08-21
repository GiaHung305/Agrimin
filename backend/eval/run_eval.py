"""Run the versioned golden dataset through the production SSE chat route."""

import asyncio
import argparse
import hashlib
import json
import os
import sys
from typing import Any
from pathlib import Path

import httpx
from google.genai import types
from google.genai.errors import ServerError
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import settings
from app.core.model_registry import ModelRole, model_name, runtime_fingerprint
from app.core.db import AsyncSessionLocal
from app.persistence.models import EvalRun, GoldenDataset
from app.services.model_gateway import ModelProviderUnavailable, generate_content


MINIMUM_JUDGE_ITEM_SCORE = 0.70


def evaluation_question_id(question: str) -> str:
    normalized = " ".join(question.casefold().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class JudgeScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=0.0, le=1.0)


def evaluation_gate(
    *,
    accuracy: float,
    citation_score: float,
    guardrail_accuracy: float,
    sample_complete: bool = True,
) -> dict[str, Any]:
    thresholds = {
        "minimum_accuracy": 0.70,
        "minimum_citation_score": 0.80,
        "minimum_guardrail_accuracy": 1.0,
    }
    checks = {
        "sample_complete": sample_complete,
        "accuracy": accuracy >= thresholds["minimum_accuracy"],
        "citation_score": citation_score >= thresholds["minimum_citation_score"],
        "guardrail_accuracy": (
            guardrail_accuracy >= thresholds["minimum_guardrail_accuracy"]
        ),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "thresholds": thresholds,
    }


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
    client: httpx.AsyncClient,
    token: str,
    question: str,
    *,
    images: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    response = await client.post(
        settings.eval_api_url,
        headers={"Authorization": f"Bearer {token}", "Accept": "text/event-stream"},
        json={"question": question, "images": images or []},
    )
    response.raise_for_status()
    return parse_sse_response(response.text)


async def llm_judge(expected: str, actual: str) -> float:
    prompt = f"""Expected answer: {expected}
Actual answer: {actual}

Score whether the actual answer contains the expected core facts."""
    response = await generate_content(
        ModelRole.JUDGE,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=JudgeScore.model_json_schema(),
        ),
    )
    return JudgeScore.model_validate_json(response.text or "").score


def citation_matches(
    expected: str | None,
    citations: list[Any],
    *,
    require_traceable: bool = False,
) -> bool:
    if not expected:
        return False
    needle = expected.casefold()
    for citation in citations:
        if (
            isinstance(citation, str)
            and not require_traceable
            and needle in citation.casefold()
        ):
            return True
        if isinstance(citation, dict):
            searchable = " ".join(
                str(citation.get(key) or "")
                for key in ("title", "source", "version", "url", "document_id", "chunk_id")
            )
            traceable = bool(
                citation.get("document_id")
                and citation.get("chunk_id")
                and citation.get("is_active") is True
            )
            if needle in searchable.casefold() and (
                not require_traceable or traceable
            ):
                return True
    return False


def merge_eval_results(
    ordered_item_ids: list[str],
    previous_results: list[dict[str, Any]],
    new_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = {result["item_id"]: result for result in previous_results}
    merged.update({result["item_id"]: result for result in new_results})
    return [
        merged[item_id]
        for item_id in ordered_item_ids
        if item_id in merged
    ]


def eval_item_needs_rerun(result: dict[str, Any] | None) -> bool:
    return result is None or bool(result.get("error"))


def summarize_eval_results(
    questions: list[Any], results: list[dict[str, Any]]
) -> dict[str, Any]:
    result_by_id = {result["item_id"]: result for result in results}
    normal_total = blocked_total = citation_total = 0
    correct = blocked_correct = citation_matches_count = complete = 0
    for item in questions:
        item_id = str(item.id)
        result = result_by_id.get(item_id)
        is_guardrail_test = item.expected_answer.startswith("BLOCKED")
        if is_guardrail_test:
            blocked_total += 1
        else:
            normal_total += 1
            citation_total += bool(item.expected_citation)
        if not result or result.get("error"):
            continue
        complete += 1
        if is_guardrail_test:
            blocked_correct += bool(result.get("guardrail_ok"))
        else:
            correct += float(result.get("judge_score") or 0.0) >= MINIMUM_JUDGE_ITEM_SCORE
            if item.expected_citation:
                citation_matches_count += bool(result.get("citation_ok"))

    accuracy = correct / normal_total if normal_total else 0.0
    citation_score = (
        citation_matches_count / citation_total if citation_total else 1.0
    )
    guardrail_accuracy = (
        blocked_correct / blocked_total if blocked_total else 1.0
    )
    gate = evaluation_gate(
        accuracy=accuracy,
        citation_score=citation_score,
        guardrail_accuracy=guardrail_accuracy,
        sample_complete=complete == len(questions),
    )
    return {
        "dataset": settings.eval_dataset_version,
        "total": len(questions),
        "complete": complete,
        "accuracy": accuracy,
        "citation_score": citation_score,
        "guardrail_accuracy": guardrail_accuracy,
        "gate": gate,
        "passed": gate["passed"],
    }


def build_eval_report(
    questions: list[Any],
    results: list[dict[str, Any]],
    *,
    response_source_dataset: str | None = None,
) -> dict[str, Any]:
    return {
        "dataset_version": settings.eval_dataset_version,
        "runtime_fingerprint": runtime_fingerprint(),
        "generation_model": model_name(ModelRole.GENERATION),
        "judge_model": model_name(ModelRole.JUDGE),
        "response_source_dataset": response_source_dataset,
        "summary": summarize_eval_results(questions, results),
        "results": results,
    }


def write_eval_report_atomic(output: Path, report: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f"{output.name}.tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(output)


def reusable_response_map(
    report: dict[str, Any], questions: list[Any]
) -> dict[str, dict[str, Any]]:
    if report.get("runtime_fingerprint") != runtime_fingerprint():
        raise ValueError("response report runtime fingerprint does not match")
    available = {
        result.get("question_id"): result
        for result in report.get("results") or []
        if result.get("question_id") and not result.get("error")
    }
    required = {
        evaluation_question_id(item.question): item for item in questions
    }
    missing = sorted(set(required).difference(available))
    if missing:
        raise ValueError(
            f"response report is missing {len(missing)} golden questions"
        )
    incomplete = [
        question_id
        for question_id in required
        if "answer" not in available[question_id]
        or "citations" not in available[question_id]
    ]
    if incomplete:
        raise ValueError(
            "response report does not contain reusable answer/citation payloads"
        )
    return {
        question_id: {
            "answer": available[question_id].get("answer") or "",
            "citations": available[question_id].get("citations") or [],
            "guardrail_status": available[question_id].get("guardrail_status"),
        }
        for question_id in required
    }


async def run_eval(
    *,
    output: Path | None = None,
    resume_from: Path | None = None,
    responses_from: Path | None = None,
) -> dict[str, Any]:
    if output is None:
        raise RuntimeError("pass --output so every evaluated item is checkpointed")
    if output.exists() and (
        not resume_from or output.resolve() != resume_from.resolve()
    ):
        raise FileExistsError(
            "existing output may only be continued from that same path"
        )

    async with AsyncSessionLocal() as db:
        query = await db.execute(
            select(GoldenDataset).where(
                GoldenDataset.dataset_version == settings.eval_dataset_version
            )
        )
        questions = query.scalars().all()
    if not questions:
        raise RuntimeError(
            f"No golden dataset rows for version {settings.eval_dataset_version!r}"
        )

    reused_responses: dict[str, dict[str, Any]] = {}
    response_source_dataset: str | None = None
    if responses_from:
        response_report = json.loads(responses_from.read_text(encoding="utf-8"))
        reused_responses = reusable_response_map(response_report, questions)
        response_source_dataset = response_report.get("dataset_version")

    ordered_item_ids = [str(item.id) for item in questions]
    previous_results: list[dict[str, Any]] = []
    if resume_from:
        previous_report = json.loads(resume_from.read_text(encoding="utf-8"))
        if previous_report.get("dataset_version") != settings.eval_dataset_version:
            raise ValueError("resume report dataset version does not match")
        if previous_report.get("runtime_fingerprint") != runtime_fingerprint():
            raise ValueError("resume report runtime fingerprint does not match")
        previous_source = previous_report.get("response_source_dataset")
        if previous_source and not responses_from:
            raise ValueError(
                "resuming a reused-response eval requires --responses-from"
            )
        if previous_source != response_source_dataset:
            raise ValueError("resume report response source does not match")
        previous_results = previous_report.get("results") or []
    previous_by_id = {
        result["item_id"]: result for result in previous_results
    }
    pending = [
        item
        for item in questions
        if eval_item_needs_rerun(previous_by_id.get(str(item.id)))
    ]
    new_results: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=90.0) as client_http:
        token = (
            None if reused_responses else await get_supabase_token(client_http)
        )
        for index, item in enumerate(pending):
            item_result: dict[str, Any] = {
                "item_id": str(item.id),
                "category": item.category,
                "guardrail_test": item.expected_answer.startswith("BLOCKED"),
            }
            try:
                question_id = evaluation_question_id(item.question)
                if reused_responses:
                    data = reused_responses[question_id]
                else:
                    data = await invoke_production_chat(
                        client_http, str(token), item.question
                    )
                if item_result["guardrail_test"]:
                    item_result["guardrail_ok"] = (
                        data.get("guardrail_status") == "block"
                    )
                else:
                    item_result["judge_score"] = await llm_judge(
                        item.expected_answer, data.get("answer", "")
                    )
                    item_result["citation_ok"] = (
                        not item.expected_citation
                        or citation_matches(
                            item.expected_citation,
                            data.get("citations", []),
                            require_traceable=True,
                        )
                    )
            except (
                httpx.HTTPError,
                ModelProviderUnavailable,
                ServerError,
                ValueError,
            ) as exc:
                item_result["error"] = type(exc).__name__
            new_results.append(item_result)
            merged = merge_eval_results(
                ordered_item_ids, previous_results, new_results
            )
            write_eval_report_atomic(
                output,
                build_eval_report(
                    questions,
                    merged,
                    response_source_dataset=response_source_dataset,
                ),
            )
            if item_result.get("error"):
                break
            if index + 1 < len(pending):
                await asyncio.sleep(settings.eval_request_delay_seconds)

    results = merge_eval_results(
        ordered_item_ids, previous_results, new_results
    )
    report = build_eval_report(
        questions,
        results,
        response_source_dataset=response_source_dataset,
    )
    write_eval_report_atomic(output, report)
    summary = report["summary"]
    if new_results and summary["gate"]["checks"]["sample_complete"]:
        async with AsyncSessionLocal() as db:
            db.add(
                EvalRun(
                    model_version=(
                        f"runtime={runtime_fingerprint()};"
                        f"generate={model_name(ModelRole.GENERATION)};"
                        f"judge={model_name(ModelRole.JUDGE)}"
                    ),
                    dataset_version=settings.eval_dataset_version,
                    accuracy=summary["accuracy"],
                    citation_score=summary["citation_score"],
                    hallucination_rate=1 - summary["guardrail_accuracy"],
                    passed=summary["passed"],
                )
            )
            await db.commit()
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume-from", type=Path)
    parser.add_argument("--responses-from", type=Path)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    report = asyncio.run(
        run_eval(
            output=args.output,
            resume_from=args.resume_from,
            responses_from=args.responses_from,
        )
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
