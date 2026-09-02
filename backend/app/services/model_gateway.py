"""Single asynchronous boundary for Gemini model calls."""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import AsyncIterator
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Any

from google import genai
from google.genai.errors import ClientError, ServerError

from app.core.config import settings
from app.core.model_registry import ModelRole, model_name
from app.core.retry_utils import gemini_retry

logger = logging.getLogger(__name__)


class ModelProviderUnavailable(RuntimeError):
    """A provider failure that callers may translate to a stable fallback."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str = "provider_unavailable",
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def _client_error_reason_code(exc: ClientError) -> str:
    """Return an operational code without logging provider response content."""
    code = getattr(exc, "code", None)
    return f"client_{code}" if isinstance(code, int) else "client_rejected"


@dataclass
class _CircuitState:
    failures: int = 0
    opened_at: float | None = None
    probe_in_progress: bool = False


_circuit_states: dict[ModelRole, _CircuitState] = {}
_circuit_lock = Lock()


def _circuit_threshold() -> int:
    return max(int(settings.model_circuit_failure_threshold), 0)


def _before_provider_call(role: ModelRole) -> None:
    """Fail fast while a role-specific provider circuit is open."""
    if _circuit_threshold() == 0:
        return
    now = monotonic()
    with _circuit_lock:
        state = _circuit_states.setdefault(role, _CircuitState())
        if state.opened_at is None:
            return
        cooldown = max(float(settings.model_circuit_cooldown_seconds), 0.0)
        if now - state.opened_at < cooldown or state.probe_in_progress:
            raise ModelProviderUnavailable(
                f"{role.value} model circuit is temporarily open",
                reason_code="circuit_open",
            )
        state.probe_in_progress = True


def provider_circuit_is_open(role: ModelRole) -> bool:
    """Read circuit state without reserving a half-open provider probe."""
    if _circuit_threshold() == 0:
        return False
    now = monotonic()
    with _circuit_lock:
        state = _circuit_states.get(role)
        if state is None or state.opened_at is None:
            return False
        cooldown = max(float(settings.model_circuit_cooldown_seconds), 0.0)
        return bool(
            state.probe_in_progress or now - state.opened_at < cooldown
        )


def _record_provider_failure(
    role: ModelRole,
    *,
    reason_code: str | None = None,
) -> None:
    threshold = _circuit_threshold()
    if threshold == 0:
        return
    now = monotonic()
    with _circuit_lock:
        state = _circuit_states.setdefault(role, _CircuitState())
        state.probe_in_progress = False
        if state.opened_at is not None:
            state.failures = threshold
            state.opened_at = now
            return
        if reason_code == "client_429":
            # Quota rejection is deterministic for the immediate window. Open
            # this role at once so later users do not repeat expensive work.
            state.failures = threshold
            state.opened_at = now
            return
        state.failures += 1
        if state.failures >= threshold:
            state.opened_at = now


def _record_provider_success(role: ModelRole) -> None:
    with _circuit_lock:
        _circuit_states.pop(role, None)


def _release_provider_probe(role: ModelRole) -> None:
    """Release a half-open probe after a non-provider exception/cancellation."""
    with _circuit_lock:
        state = _circuit_states.get(role)
        if state is not None:
            state.probe_in_progress = False


def _reset_circuit_breakers() -> None:
    """Clear process-local state for deterministic tests and lifecycle resets."""
    with _circuit_lock:
        _circuit_states.clear()


client: genai.Client | None = None


def _get_client() -> genai.Client:
    """Create the provider client only when a model call is attempted."""
    global client
    if client is not None:
        return client
    if not settings.google_api_key:
        raise ModelProviderUnavailable(
            "Google API key is not configured",
            reason_code="api_key_missing",
        )
    client = genai.Client(api_key=settings.google_api_key)
    return client


@gemini_retry
async def _generate_content_with_retry(
    role: ModelRole,
    contents: Any,
    *,
    config: Any | None = None,
) -> Any:
    try:
        return await asyncio.wait_for(
            _get_client().aio.models.generate_content(
                model=model_name(role),
                contents=contents,
                config=config,
            ),
            timeout=settings.model_request_timeout_seconds,
        )
    except TimeoutError as exc:
        raise ModelProviderUnavailable(
            f"{role.value} model request timed out",
            reason_code="request_timeout",
        ) from exc
    except ClientError as exc:
        raise ModelProviderUnavailable(
            f"{role.value} model request was rejected by provider",
            reason_code=_client_error_reason_code(exc),
        ) from exc


async def generate_content(
    role: ModelRole,
    contents: Any,
    *,
    config: Any | None = None,
) -> Any:
    _before_provider_call(role)
    try:
        response = await _generate_content_with_retry(
            role, contents, config=config
        )
    except (ModelProviderUnavailable, ServerError) as exc:
        logger.warning(
            "Model provider call failed role=%s error=%s reason_code=%s",
            role.value,
            type(exc).__name__,
            getattr(exc, "reason_code", "server_error"),
        )
        _record_provider_failure(
            role, reason_code=getattr(exc, "reason_code", "server_error")
        )
        raise
    except BaseException:
        _release_provider_probe(role)
        raise
    _record_provider_success(role)
    return response


async def _open_stream(role: ModelRole, contents: str) -> Any:
    try:
        return await asyncio.wait_for(
            _get_client().aio.models.generate_content_stream(
                model=model_name(role),
                contents=contents,
            ),
            timeout=settings.model_request_timeout_seconds,
        )
    except TimeoutError as exc:
        raise ModelProviderUnavailable(
            f"{role.value} model stream timed out",
            reason_code="stream_timeout",
        ) from exc
    except ClientError as exc:
        raise ModelProviderUnavailable(
            f"{role.value} model stream was rejected by provider",
            reason_code=_client_error_reason_code(exc),
        ) from exc


async def _next_stream_chunk(role: ModelRole, iterator: Any) -> Any:
    try:
        return await asyncio.wait_for(
            anext(iterator),
            timeout=settings.model_request_timeout_seconds,
        )
    except TimeoutError as exc:
        raise ModelProviderUnavailable(
            f"{role.value} model stream timed out",
            reason_code="stream_timeout",
        ) from exc
    except ClientError as exc:
        raise ModelProviderUnavailable(
            f"{role.value} model stream was rejected by provider",
            reason_code=_client_error_reason_code(exc),
        ) from exc


def _is_retryable_stream_error(exc: BaseException) -> bool:
    return isinstance(exc, ServerError) or (
        isinstance(exc, ModelProviderUnavailable)
        and exc.reason_code == "stream_timeout"
    )


async def _sleep_before_stream_retry(attempt: int) -> None:
    """Use bounded exponential backoff with jitter between stream attempts."""
    maximum = min(2.0**attempt, 4.0)
    await asyncio.sleep(random.uniform(0.5, maximum))


async def _start_stream_with_retry(role: ModelRole, contents: str) -> tuple[Any, Any]:
    """Retry only before the first chunk, while nothing reached the client."""
    for attempt in range(1, 3):
        try:
            stream = await _open_stream(role, contents)
            iterator = stream.__aiter__()
            first_chunk = await _next_stream_chunk(role, iterator)
            return iterator, first_chunk
        except (ModelProviderUnavailable, ServerError) as exc:
            if attempt == 2 or not _is_retryable_stream_error(exc):
                raise
            logger.warning(
                "Retrying model stream role=%s attempt=%s reason_code=%s",
                role.value,
                attempt + 1,
                getattr(exc, "reason_code", "server_error"),
            )
            await _sleep_before_stream_retry(attempt)
    raise RuntimeError("unreachable stream retry state")


async def stream_content(role: ModelRole, contents: str) -> AsyncIterator[Any]:
    """Stream live; retry transient failures only before emitting a first chunk."""
    _before_provider_call(role)
    try:
        try:
            iterator, first_chunk = await _start_stream_with_retry(role, contents)
        except StopAsyncIteration:
            _record_provider_success(role)
            return
        yield first_chunk
        while True:
            try:
                yield await _next_stream_chunk(role, iterator)
            except StopAsyncIteration:
                break
    except (ModelProviderUnavailable, ServerError) as exc:
        logger.warning(
            "Model provider stream failed role=%s error=%s reason_code=%s",
            role.value,
            type(exc).__name__,
            getattr(exc, "reason_code", "server_error"),
        )
        _record_provider_failure(
            role, reason_code=getattr(exc, "reason_code", "server_error")
        )
        raise
    except BaseException:
        _release_provider_probe(role)
        raise
    _record_provider_success(role)
