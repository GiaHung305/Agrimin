import asyncio
import logging
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.repository.models import (
    CropSeason,
    DeviceToken,
    FarmMonitoringSchedule,
    FarmPlot,
    FarmRecommendation,
    FarmRiskPrediction,
    FarmTask,
    FarmWeatherObservation,
    Notification,
    NotificationDelivery,
    PendingAction,
)
from app.services.farm_monitoring import (
    build_recommendation_body,
    highest_risk_assessment,
    local_now_naive,
    prediction_expiry,
    recommendation_dedupe_key,
    resolve_monitoring_policy,
    schedule_run_key,
)
from app.services.push_service import send_push
from app.tools.mcp_weather_client import geocode_province_via_mcp, get_weather_via_mcp

logger = logging.getLogger(__name__)
MAX_PUSH_ATTEMPTS = 5


async def _notify(
    session,
    user_id,
    kind: str,
    title: str,
    body: str,
    dedupe_key: str,
    *,
    push_enabled: bool = True,
) -> tuple[Notification, bool]:
    existing = (
        await session.execute(
            select(Notification).where(Notification.dedupe_key == dedupe_key)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False
    notice = Notification(
        user_id=user_id,
        kind=kind,
        title=title,
        body=body,
        dedupe_key=dedupe_key,
        delivered_at=local_now_naive(),
    )
    session.add(notice)
    await session.flush()
    if push_enabled:
        tokens = (
            await session.execute(
                select(DeviceToken).where(
                    DeviceToken.user_id == user_id,
                    DeviceToken.active.is_(True),
                )
            )
        ).scalars().all()
        for device in tokens:
            delivery = NotificationDelivery(
                user_id=user_id,
                notification_id=notice.id,
                device_token_id=device.id,
                delivery_key=f"{notice.id}:{device.id}",
                status="pending",
                attempt_count=0,
                next_attempt_at=local_now_naive(),
            )
            session.add(delivery)
    return notice, True


def _push_retry_at(now, attempt_count: int):
    delay_minutes = min(2 ** max(attempt_count - 1, 0), 60)
    return now + timedelta(minutes=delay_minutes)


async def process_push_deliveries_once() -> None:
    now = local_now_naive()
    async with AsyncSessionLocal() as session:
        deliveries = (
            await session.execute(
                select(NotificationDelivery)
                .where(
                    NotificationDelivery.status.in_(("pending", "retry")),
                    NotificationDelivery.next_attempt_at <= now,
                )
                .order_by(NotificationDelivery.next_attempt_at.asc())
                .limit(100)
                .with_for_update(skip_locked=True)
            )
        ).scalars().all()
        for delivery in deliveries:
            notice = (
                await session.execute(
                    select(Notification).where(
                        Notification.id == delivery.notification_id,
                        Notification.user_id == delivery.user_id,
                    )
                )
            ).scalar_one_or_none()
            device = (
                await session.execute(
                    select(DeviceToken).where(
                        DeviceToken.id == delivery.device_token_id,
                        DeviceToken.user_id == delivery.user_id,
                        DeviceToken.active.is_(True),
                    )
                )
            ).scalar_one_or_none()
            delivery.attempt_count += 1
            delivery.last_attempt_at = now
            delivery.updated_at = now
            if notice is None or device is None:
                delivery.status = "cancelled"
                delivery.last_error_code = "delivery_target_unavailable"
                continue
            try:
                delivered = await send_push(device.token, notice.title, notice.body)
            except Exception as exc:
                delivered = False
                logger.warning(
                    "Push delivery attempt raised an exception",
                    extra={
                        "delivery_id": str(delivery.id),
                        "error_type": type(exc).__name__,
                    },
                )
            if delivered:
                delivery.status = "delivered"
                delivery.delivered_at = now
                delivery.last_error_code = None
            elif delivery.attempt_count >= MAX_PUSH_ATTEMPTS:
                delivery.status = "failed"
                delivery.last_error_code = "push_delivery_failed"
            else:
                delivery.status = "retry"
                delivery.next_attempt_at = _push_retry_at(now, delivery.attempt_count)
                delivery.last_error_code = "push_delivery_failed"
        await session.commit()


async def _expire_recommendations(session, now) -> int:
    recommendations = (
        await session.execute(
            select(FarmRecommendation)
            .where(
                FarmRecommendation.status.in_(("proposed", "notified")),
                FarmRecommendation.expires_at <= now,
            )
            .with_for_update(skip_locked=True)
        )
    ).scalars().all()
    for recommendation in recommendations:
        recommendation.status = "expired"
        recommendation.resolved_at = now
        if recommendation.pending_action_id is None:
            continue
        action = (
            await session.execute(
                select(PendingAction)
                .where(
                    PendingAction.id == recommendation.pending_action_id,
                    PendingAction.user_id == recommendation.user_id,
                    PendingAction.status == "pending",
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if action is not None:
            action.status = "expired"
    return len(recommendations)


async def _run_monitoring_schedule(session, schedule, now) -> None:
    scheduled_for = schedule.next_run_at
    run_key = schedule_run_key(schedule.id, scheduled_for)
    existing = (
        await session.execute(
            select(FarmWeatherObservation).where(
                FarmWeatherObservation.run_key == run_key
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        schedule.last_run_at = now
        schedule.next_run_at = now + timedelta(hours=schedule.frequency_hours)
        schedule.last_error_code = None
        return

    plot = None
    if schedule.plot_id is not None:
        plot = (
            await session.execute(
                select(FarmPlot).where(
                    FarmPlot.id == schedule.plot_id,
                    FarmPlot.user_id == schedule.user_id,
                    FarmPlot.status == "active",
                )
            )
        ).scalar_one_or_none()
    if (
        plot is not None
        and plot.latitude is not None
        and plot.longitude is not None
    ):
        coords = (plot.latitude, plot.longitude)
        coordinate_source = "plot_gps"
    else:
        coords = await geocode_province_via_mcp(schedule.province)
        coordinate_source = "province_geocode"
    if not coords:
        raise RuntimeError("monitoring_geocode_not_found")
    season = None
    if schedule.crop_season_id is not None:
        season = (
            await session.execute(
                select(CropSeason).where(
                    CropSeason.id == schedule.crop_season_id,
                    CropSeason.user_id == schedule.user_id,
                    CropSeason.status == "active",
                )
            )
        ).scalar_one_or_none()
    growth_stage = getattr(season, "growth_stage", None)
    forecast = (await get_weather_via_mcp(*coords)).get("forecast", [])
    policy = resolve_monitoring_policy(schedule.crop, growth_stage)
    assessment = highest_risk_assessment(forecast, policy)
    expires_at = prediction_expiry(now, schedule.frequency_hours)

    observation = FarmWeatherObservation(
        user_id=schedule.user_id,
        schedule_id=schedule.id,
        run_key=run_key,
        source="openweathermap_forecast_v2.5",
        forecast_date=assessment.forecast_date,
        inputs={
            "province": schedule.province,
            "plot_id": str(schedule.plot_id),
            "crop_season_id": str(schedule.crop_season_id),
            "growth_stage": growth_stage,
            "growth_stage_key": policy.growth_stage_key,
            "coordinates": {"latitude": coords[0], "longitude": coords[1]},
            "coordinate_source": coordinate_source,
            "location_accuracy_m": (
                plot.location_accuracy_m if coordinate_source == "plot_gps" else None
            ),
            "elevation_m": (
                plot.elevation_m if coordinate_source == "plot_gps" else None
            ),
            "forecast": forecast,
        },
        observed_at=now,
        expires_at=expires_at,
    )
    session.add(observation)
    await session.flush()
    prediction = FarmRiskPrediction(
        user_id=schedule.user_id,
        schedule_id=schedule.id,
        observation_id=observation.id,
        risk_type=policy.risk_type,
        risk_level=assessment.risk_level,
        confidence=assessment.confidence,
        policy_version=policy.version,
        inputs={
            **assessment.inputs,
            "reasons": list(assessment.reasons),
            "crop": schedule.crop,
            "province": schedule.province,
            "growth_stage": growth_stage,
            "growth_stage_key": policy.growth_stage_key,
        },
        expires_at=expires_at,
        created_at=now,
    )
    session.add(prediction)
    await session.flush()

    if assessment.risk_level == "high":
        dedupe_key = recommendation_dedupe_key(
            schedule.id, assessment.forecast_date, policy.version
        )
        recommendation = FarmRecommendation(
            user_id=schedule.user_id,
            schedule_id=schedule.id,
            prediction_id=prediction.id,
            kind="crop_weather_risk_check",
            title=policy.alert_title,
            body=build_recommendation_body(
                province=schedule.province,
                assessment=assessment,
                policy=policy,
            ),
            status="proposed",
            dedupe_key=dedupe_key,
            expires_at=expires_at,
            created_at=now,
        )
        session.add(recommendation)
        await session.flush()
        recommended_due_at = datetime.combine(
            assessment.forecast_date, time(hour=7)
        )
        if recommended_due_at <= now:
            recommended_due_at = now + timedelta(hours=1)
        action = PendingAction(
            user_id=schedule.user_id,
            conversation_id=None,
            action_type="create_task",
            payload={
                "title": policy.task_title,
                "description": recommendation.body,
                "due_at": recommended_due_at.isoformat(),
                "source": "farm_monitoring",
                "schedule_id": str(schedule.id),
                "prediction_id": str(prediction.id),
            },
            status="pending",
            expires_at=(
                datetime.now(timezone.utc).replace(tzinfo=None)
                + timedelta(hours=max(6, schedule.frequency_hours))
            ),
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(action)
        await session.flush()
        recommendation.pending_action_id = action.id
        notice, _ = await _notify(
            session,
            schedule.user_id,
            "crop_weather_risk",
            recommendation.title,
            recommendation.body,
            dedupe_key,
            push_enabled=schedule.notification_scope == "push_and_in_app",
        )
        recommendation.notification_id = notice.id
        recommendation.status = "notified"

    schedule.last_run_at = now
    schedule.next_run_at = now + timedelta(hours=schedule.frequency_hours)
    schedule.last_error_code = None


async def _run_monitoring_schedule_isolated(session, schedule, now) -> bool:
    """Run one farm schedule atomically without poisoning the whole cycle."""
    try:
        async with session.begin_nested():
            await _run_monitoring_schedule(session, schedule, now)
        return True
    except Exception as exc:
        # The savepoint rolls back any observation/prediction/recommendation
        # flushed before the failure. Retry only this schedule later.
        schedule.last_error_code = "weather_monitoring_unavailable"
        schedule.next_run_at = now + timedelta(minutes=15)
        logger.warning(
            "Farm monitoring schedule failed",
            extra={
                "schedule_id": str(schedule.id),
                "error_type": type(exc).__name__,
            },
        )
        return False


async def process_due_tasks_once() -> None:
    now = local_now_naive()
    async with AsyncSessionLocal() as session:
        tasks = (
            await session.execute(
                select(FarmTask)
                .where(FarmTask.status == "open", FarmTask.due_at <= now)
                .order_by(FarmTask.due_at.asc())
                .limit(100)
                .with_for_update(skip_locked=True)
            )
        ).scalars().all()
        for task in tasks:
            await _notify(
                session,
                task.user_id,
                "task_due",
                "Việc cần làm",
                task.title,
                f"task:{task.id}:due",
            )
        await session.commit()


async def process_monitoring_schedules_once() -> None:
    now = local_now_naive()
    async with AsyncSessionLocal() as session:
        await _expire_recommendations(session, now)
        schedules = (
            await session.execute(
                select(FarmMonitoringSchedule)
                .join(
                    CropSeason,
                    FarmMonitoringSchedule.crop_season_id == CropSeason.id,
                )
                .where(
                    FarmMonitoringSchedule.status == "active",
                    FarmMonitoringSchedule.consent_granted_at.is_not(None),
                    FarmMonitoringSchedule.next_run_at.is_not(None),
                    FarmMonitoringSchedule.next_run_at <= now,
                    CropSeason.status == "active",
                )
                .with_for_update(skip_locked=True)
            )
        ).scalars().all()
        for schedule in schedules:
            await _run_monitoring_schedule_isolated(session, schedule, now)
        await session.commit()


async def run_reminders_once() -> None:
    """Run one complete pass for diagnostics and backwards compatibility."""
    await process_due_tasks_once()
    await process_monitoring_schedules_once()


async def _run_periodically(operation, error_message: str) -> None:
    while True:
        try:
            await operation()
        except Exception:
            logger.exception(error_message)
        await asyncio.sleep(settings.assistant_worker_poll_seconds)


async def main():
    await asyncio.gather(
        _run_periodically(
            process_due_tasks_once,
            "Task reminder cycle failed",
        ),
        _run_periodically(
            process_monitoring_schedules_once,
            "Farm monitoring cycle failed",
        ),
        _run_periodically(
            process_push_deliveries_once,
            "Push delivery cycle failed",
        ),
    )


if __name__ == "__main__":
    asyncio.run(main())
