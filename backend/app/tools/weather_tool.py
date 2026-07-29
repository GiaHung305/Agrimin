import json
import httpx

from app.core.redis_client import redis_client
from app.core.config import settings

CACHE_TTL_SECONDS = 900  # 15 phút, đúng thiết kế Sprint 0


async def get_weather(latitude: float, longitude: float) -> dict:
    """
    Realtime Tool — tách biệt khỏi RAG tĩnh (Qdrant), vì dữ liệu thời tiết
    thay đổi liên tục, cache ngắn hạn 15 phút thay vì lưu vào vector search.
    """
    cache_key = f"weather:{round(latitude, 2)}:{round(longitude, 2)}"

    cached = await redis_client.get(cache_key)
    if cached:
        data = json.loads(cached)
        data["from_cache"] = True
        return data

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://api.openweathermap.org/data/2.5/forecast",
            params={
                "lat": latitude,
                "lon": longitude,
                "appid": settings.openweather_api_key,
                "units": "metric",
                "lang": "vi",
            },
        )
        response.raise_for_status()
        data = response.json()

    # Rút gọn dữ liệu 3 ngày tới, tránh đưa nguyên response khổng lồ vào prompt
    forecast_summary = []
    seen_dates = set()
    for entry in data.get("list", []):
        date = entry["dt_txt"].split(" ")[0]
        if date not in seen_dates and len(seen_dates) < 3:
            seen_dates.add(date)
            forecast_summary.append({
                "date": date,
                "temp": entry["main"]["temp"],
                "description": entry["weather"][0]["description"],
                "rain_probability": entry.get("pop", 0),
            })

    result = {"forecast": forecast_summary, "from_cache": False}

    await redis_client.set(cache_key, json.dumps(result), ex=CACHE_TTL_SECONDS)

    return result