import httpx
import json

from app.core.redis_client import redis_client
from app.core.config import settings

CACHE_TTL_SECONDS = 86400  # 24h, tọa độ tỉnh không đổi


async def geocode_province(province: str, country_code: str = "VN") -> tuple[float, float] | None:
    """
    Geocoding qua OpenWeatherMap Geocoding API — cùng provider với Weather,
    dùng chung API key, tránh phụ thuộc thêm 1 dịch vụ khác không cần thiết.
    """
    cache_key = f"geocode:{province.lower().strip()}"
    cached = await redis_client.get(cache_key)
    if cached:
        lat, lon = json.loads(cached)
        return lat, lon

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://api.openweathermap.org/geo/1.0/direct",
            params={
                "q": f"{province},{country_code}",
                "limit": 1,
                "appid": settings.openweather_api_key,
            },
        )
        response.raise_for_status()
        results = response.json()

    if not results:
        return None

    lat, lon = results[0]["lat"], results[0]["lon"]
    await redis_client.set(cache_key, json.dumps([lat, lon]), ex=CACHE_TTL_SECONDS)

    return lat, lon