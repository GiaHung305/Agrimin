import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.db import AsyncSessionLocal
from app.repository.models import DeviceToken, FarmProfile, FarmTask, Notification
from app.services.push_service import send_push
from app.tools.mcp_weather_client import geocode_province_via_mcp, get_weather_via_mcp

logger = logging.getLogger(__name__)
_LOCAL_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _local_now_naive() -> datetime:
    """Vietnam time matching the current timezone-naive task DateTime columns."""
    return datetime.now(_LOCAL_TZ).replace(tzinfo=None)


async def _notify(session, user_id, kind: str, title: str, body: str, dedupe_key: str):
    if (await session.execute(select(Notification).where(Notification.dedupe_key == dedupe_key))).scalar_one_or_none():
        return
    notice = Notification(user_id=user_id, kind=kind, title=title, body=body, dedupe_key=dedupe_key, delivered_at=_local_now_naive())
    session.add(notice)
    tokens = (await session.execute(select(DeviceToken).where(DeviceToken.user_id == user_id, DeviceToken.active == True))).scalars().all()
    for device in tokens:
        await send_push(device.token, title, body)


async def run_reminders_once():
    now = _local_now_naive()
    async with AsyncSessionLocal() as session:
        tasks = (await session.execute(select(FarmTask).where(FarmTask.status == "open", FarmTask.due_at <= now))).scalars().all()
        for task in tasks:
            await _notify(session, task.user_id, "task_due", "Việc cần làm", task.title, f"task:{task.id}:due")
        profiles = (await session.execute(select(FarmProfile).where(FarmProfile.province.is_not(None)))).scalars().all()
        for profile in profiles:
            try:
                coords = await geocode_province_via_mcp(profile.province)
                if not coords:
                    continue
                forecast = (await get_weather_via_mcp(*coords)).get("forecast", [])
            except Exception:
                # Weather is optional. Continue the cycle so due-task records
                # are committed and other farms are not starved by one outage.
                logger.warning("Weather reminder lookup failed", exc_info=True)
                continue
            rainy = next((day for day in forecast if day.get("rain_probability", 0) >= 0.7), None)
            if rainy:
                await _notify(session, profile.user_id, "weather_alert", "Cảnh báo thời tiết", f"Khả năng mưa cao tại {profile.province} ngày {rainy['date']}. Hãy kiểm tra kế hoạch cho {profile.crop or 'cây trồng'}.", f"weather:{profile.id}:{rainy['date']}")
        await session.commit()


async def main():
    while True:
        try:
            await run_reminders_once()
        except Exception:
            logger.exception("Assistant reminder cycle failed")
        await asyncio.sleep(15 * 60)


if __name__ == "__main__":
    asyncio.run(main())
