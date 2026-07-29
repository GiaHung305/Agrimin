from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.core.config import settings

MCP_SERVER_URL = settings.mcp_weather_url


async def call_mcp_tool(tool_name: str, arguments: dict) -> dict:
    async with streamablehttp_client(MCP_SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            return result.structured_content


async def get_weather_via_mcp(latitude: float, longitude: float) -> dict:
    return await call_mcp_tool("get_weather", {"latitude": latitude, "longitude": longitude})


async def geocode_province_via_mcp(province: str) -> dict:
    result = await call_mcp_tool("geocode_province", {"province": province})
    if result.get("found"):
        return (result["latitude"], result["longitude"])
    return None