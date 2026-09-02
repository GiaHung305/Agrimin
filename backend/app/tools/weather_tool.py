import json
import logging
from datetime import datetime

import httpx

from app.core.config import settings
from app.core.redis_client import redis_client
from app.tools.weather_contract import LOCAL_WEATHER_TZ


CACHE_TTL_SECONDS = 900
logging.getLogger("httpx").setLevel(logging.WARNING)


async def get_weather(latitude: float, longitude: float) -> dict:
    """Return a compact three-day forecast for the realtime weather tool."""
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

    result = {
        "forecast": summarize_forecast(data.get("list", [])),
        "from_cache": False,
    }
    await redis_client.set(cache_key, json.dumps(result), ex=CACHE_TTL_SECONDS)
    return result


def summarize_forecast(entries: list[dict], max_days: int = 3) -> list[dict]:
    """Aggregate OpenWeather's 3-hour intervals into deterministic daily data."""
    grouped: dict[str, list[dict]] = {}
    for entry in entries:
        timestamp = entry.get("dt")
        date_text = ""
        if timestamp is not None and not isinstance(timestamp, bool):
            try:
                date_text = datetime.fromtimestamp(
                    float(timestamp),
                    LOCAL_WEATHER_TZ,
                ).date().isoformat()
            except (OSError, OverflowError, TypeError, ValueError):
                date_text = ""
        if not date_text:
            # Legacy fixtures and defensive provider fallback. Production
            # OpenWeather rows include ``dt`` and therefore use Vietnam time.
            date_text = str(entry.get("dt_txt", "")).split(" ")[0]
        if not date_text:
            continue
        if date_text not in grouped and len(grouped) >= max_days:
            continue
        grouped.setdefault(date_text, []).append(entry)

    summary: list[dict] = []
    for date_text, day_entries in grouped.items():
        temperatures = [
            float(entry["main"]["temp"])
            for entry in day_entries
            if entry.get("main", {}).get("temp") is not None
        ]
        minimums = [
            float(entry["main"].get("temp_min", entry["main"]["temp"]))
            for entry in day_entries
            if entry.get("main", {}).get("temp") is not None
        ]
        maximums = [
            float(entry["main"].get("temp_max", entry["main"]["temp"]))
            for entry in day_entries
            if entry.get("main", {}).get("temp") is not None
        ]
        humidities = [
            float(entry["main"]["humidity"])
            for entry in day_entries
            if entry.get("main", {}).get("humidity") is not None
        ]
        rain_probability = max(
            (float(entry.get("pop", 0) or 0) for entry in day_entries),
            default=0.0,
        )
        rain_mm = sum(
            float(entry.get("rain", {}).get("3h", 0) or 0)
            for entry in day_entries
        )
        representative = max(
            day_entries,
            key=lambda entry: float(entry.get("pop", 0) or 0),
        )
        weather = representative.get("weather") or [{}]
        summary.append(
            {
                "date": date_text,
                "temp": (
                    round(sum(temperatures) / len(temperatures), 1)
                    if temperatures
                    else None
                ),
                "temp_min": min(minimums) if minimums else None,
                "temp_max": max(maximums) if maximums else None,
                "humidity": (
                    round(sum(humidities) / len(humidities), 1)
                    if humidities
                    else None
                ),
                "humidity_max": max(humidities) if humidities else None,
                "description": weather[0].get("description"),
                "rain_probability": rain_probability,
                "rain_mm": round(rain_mm, 1),
            }
        )
    return summary
