import sys
import os
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp import server as fastmcp_server

from app.tools.weather_tool import get_weather as _get_weather
from app.tools.geocoding_tool import geocode_province as _geocode_province

# httpx logs full query strings at INFO, including the OpenWeather ``appid``.
# Keep dependency logs at WARNING so credentials never enter container logs.
logging.getLogger("httpx").setLevel(logging.WARNING)

# The installed MCP SDK leaves the generic lifespan annotation unresolved in
# its Pydantic Settings model. Resolve it before Settings reads environment
# sources so startup stays warning-free and lifespan values remain parseable.
fastmcp_server.Settings.model_rebuild(_types_namespace=vars(fastmcp_server))

mcp = FastMCP("AgriMind Weather Tools", host="0.0.0.0", port=8002)

@mcp.tool()
async def get_weather(latitude: float, longitude: float) -> dict:
    """Lấy dự báo thời tiết 3 ngày tới cho 1 tọa độ (dùng cache Redis TTL 15 phút)."""
    return await _get_weather(latitude, longitude)


@mcp.tool()
async def geocode_province(province: str) -> dict:
    """Tìm tọa độ (lat, lon) của 1 tỉnh Việt Nam qua OpenWeatherMap Geocoding."""
    coords = await _geocode_province(province)
    if coords is None:
        return {"found": False}
    lat, lon = coords
    return {"found": True, "latitude": lat, "longitude": lon}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
