"""Single asynchronous boundary for Gemini model calls."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from google import genai

from app.core.config import settings
from app.core.model_registry import ModelRole, model_name
from app.core.retry_utils import gemini_retry


client = genai.Client(api_key=settings.google_api_key)


class ModelProviderUnavailable(RuntimeError):
    """A provider timeout that callers may translate to a stable fallback."""


@gemini_retry
async def generate_content(
    role: ModelRole,
    contents: str,
    *,
    config: Any | None = None,
) -> Any:
    try:
        return await asyncio.wait_for(
            client.aio.models.generate_content(
                model=model_name(role),
                contents=contents,
                config=config,
            ),
            timeout=settings.model_request_timeout_seconds,
        )
    except TimeoutError as exc:
        raise ModelProviderUnavailable(f"{role.value} model request timed out") from exc


@gemini_retry
async def _open_stream(role: ModelRole, contents: str) -> Any:
    return await asyncio.wait_for(
        client.aio.models.generate_content_stream(
            model=model_name(role),
            contents=contents,
        ),
        timeout=settings.model_request_timeout_seconds,
    )


async def stream_content(role: ModelRole, contents: str) -> AsyncIterator[Any]:
    """Stream chunks while applying a timeout to connect and every read."""
    try:
        stream = await _open_stream(role, contents)
        iterator = stream.__aiter__()
        while True:
            try:
                yield await asyncio.wait_for(
                    anext(iterator), timeout=settings.model_request_timeout_seconds
                )
            except StopAsyncIteration:
                break
    except TimeoutError as exc:
        raise ModelProviderUnavailable(f"{role.value} model stream timed out") from exc
