"""Compatibility adapter for the external MCP weather service."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.core.config import settings

MCP_SERVER_URL = settings.mcp_weather_url


class MCPToolResponseError(RuntimeError):
    pass


def extract_structured_content(result: Any) -> dict:
    """Read both current camelCase and legacy snake_case MCP SDK shapes."""
    structured = getattr(result, "structuredContent", None)
    if structured is None:
        structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured

    # Older or unstructured servers may only return JSON in a text block.
    for block in getattr(result, "content", []) or []:
        text = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    raise MCPToolResponseError("MCP weather tool returned no structured object")


async def call_mcp_tool(tool_name: str, arguments: dict) -> dict:
    async with asyncio.timeout(settings.mcp_request_timeout_seconds):
        async with streamablehttp_client(MCP_SERVER_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                return extract_structured_content(result)


async def get_weather_via_mcp(latitude: float, longitude: float) -> dict:
    return await call_mcp_tool(
        "get_weather", {"latitude": latitude, "longitude": longitude}
    )


async def geocode_province_via_mcp(province: str) -> tuple[float, float] | None:
    result = await call_mcp_tool("geocode_province", {"province": province})
    if result.get("found"):
        return result["latitude"], result["longitude"]
    return None
