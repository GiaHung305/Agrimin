"""Compatibility adapter for the external MCP weather service."""

from __future__ import annotations

import asyncio
import json
import math
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.core.config import settings
from app.tools.weather_contract import WeatherContractError, normalize_weather_result

MCP_SERVER_URL = settings.mcp_weather_url
VIETNAM_LATITUDE_RANGE = (8.0, 24.5)
VIETNAM_LONGITUDE_RANGE = (102.0, 110.5)


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
    result = await call_mcp_tool(
        "get_weather", {"latitude": latitude, "longitude": longitude}
    )
    try:
        return normalize_weather_result(result)
    except WeatherContractError as exc:
        raise MCPToolResponseError("MCP weather tool returned invalid data") from exc


async def geocode_province_via_mcp(province: str) -> tuple[float, float] | None:
    result = await call_mcp_tool("geocode_province", {"province": province})
    if result.get("found") is False:
        return None
    if result.get("found") is not True:
        raise MCPToolResponseError("MCP geocoding tool returned invalid data")
    latitude = result.get("latitude")
    longitude = result.get("longitude")
    if isinstance(latitude, bool) or isinstance(longitude, bool):
        raise MCPToolResponseError("MCP geocoding tool returned invalid data")
    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError) as exc:
        raise MCPToolResponseError("MCP geocoding tool returned invalid data") from exc
    if (
        not math.isfinite(latitude)
        or not math.isfinite(longitude)
        or not VIETNAM_LATITUDE_RANGE[0]
        <= latitude
        <= VIETNAM_LATITUDE_RANGE[1]
        or not VIETNAM_LONGITUDE_RANGE[0]
        <= longitude
        <= VIETNAM_LONGITUDE_RANGE[1]
    ):
        raise MCPToolResponseError("MCP geocoding tool returned invalid data")
    return latitude, longitude
