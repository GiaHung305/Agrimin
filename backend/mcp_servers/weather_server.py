import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcp.server.fastmcp import FastMCP

from app.tools.weather_tool import get_weather as _get_weather
from app.tools.geocoding_tool import geocode_province as _geocode_province

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