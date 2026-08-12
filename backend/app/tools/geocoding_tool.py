import httpx
import json
import logging

from app.core.redis_client import redis_client
from app.core.config import settings
from app.services.vietnam_regions import province_geocode_fallback

CACHE_TTL_SECONDS = 86400  # 24h, tọa độ tỉnh không đổi
logging.getLogger("httpx").setLevel(logging.WARNING)


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

    queries = [province.strip()]
    fallback = province_geocode_fallback(province)
    if fallback and fallback.casefold() != province.strip().casefold():
        queries.append(fallback)

    results = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for query in queries:
            response = await client.get(
                "https://api.openweathermap.org/geo/1.0/direct",
                params={
                    "q": f"{query},{country_code}",
                    "limit": 1,
                    "appid": settings.openweather_api_key,
                },
            )
            response.raise_for_status()
            results = response.json()
            if results:
                break

    if not results:
        return None

    lat, lon = results[0]["lat"], results[0]["lon"]
    await redis_client.set(cache_key, json.dumps([lat, lon]), ex=CACHE_TTL_SECONDS)

    return lat, lon
