from datetime import date, datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.db import get_db
from app.repository.models import (
    DeviceToken,
    CropSeason,
    FarmLog,
    FarmMonitoringSchedule,
    FarmPlot,
    FarmProfile,
    FarmRiskPrediction,
    FarmRecommendation,
    FarmTask,
    Notification,
    PendingAction,
)
from app.services.farm_monitoring import (
    is_supported_crop,
    is_supported_region,
    local_now_naive,
    resolve_monitoring_policy,
)

router = APIRouter(prefix="/assistant", tags=["assistant"])


class FarmProfileRequest(BaseModel):
    name: str = Field(default="Nông trại của tôi", max_length=255)
    province: str | None = Field(default=None, max_length=100)
    crop: str | None = Field(default=None, max_length=100)
    area_ha: float | None = Field(default=None, ge=0)
    farming_style: str | None = Field(default=None, max_length=255)


class DeviceTokenRequest(BaseModel):
    token: str = Field(min_length=10, max_length=512)
    platform: str = Field(pattern="^(android|ios|web)$")


class TaskUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    due_at: datetime | None = None
    status: Literal["open", "completed", "cancelled"] | None = None


class MonitoringScheduleCreateRequest(BaseModel):
    consent: bool
    crop_season_id: str
    frequency_hours: Literal[6, 12, 24] = 24
    notification_scope: Literal["in_app", "push_and_in_app"] = "in_app"


class MonitoringScheduleUpdateRequest(BaseModel):
    status: Literal["active", "paused"] | None = None
    frequency_hours: Literal[6, 12, 24] | None = None
    notification_scope: Literal["in_app", "push_and_in_app"] | None = None


class FarmPlotCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    area_ha: float | None = Field(default=None, gt=0)
    location_note: str | None = Field(default=None, max_length=500)


class FarmPlotUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    area_ha: float | None = Field(default=None, gt=0)
    location_note: str | None = Field(default=None, max_length=500)


class CropSeasonCreateRequest(BaseModel):
    crop: str = Field(min_length=1, max_length=100)
    variety: str | None = Field(default=None, max_length=100)
    growth_stage: str | None = Field(default=None, max_length=100)
    planted_on: date | None = None
    expected_harvest_on: date | None = None
    status: Literal["planned", "active"] = "active"


class CropSeasonUpdateRequest(BaseModel):
    crop: str | None = Field(default=None, min_length=1, max_length=100)
    variety: str | None = Field(default=None, max_length=100)
    growth_stage: str | None = Field(default=None, max_length=100)
    planted_on: date | None = None
    expected_harvest_on: date | None = None
    status: Literal["planned", "active", "completed", "cancelled"] | None = None


def _profile_payload(profile: FarmProfile) -> dict:
    return {key: getattr(profile, key) for key in ("id", "name", "province", "crop", "area_ha", "farming_style")}


def _prediction_payload(prediction: FarmRiskPrediction | None) -> dict | None:
    if prediction is None:
        return None
    return {
        "id": str(prediction.id),
        "risk_type": prediction.risk_type,
        "risk_level": prediction.risk_level,
        "confidence": prediction.confidence,
        "policy_version": prediction.policy_version,
        "inputs": prediction.inputs,
        "expires_at": prediction.expires_at,
        "created_at": prediction.created_at,
    }


def _schedule_payload(
    schedule: FarmMonitoringSchedule,
    latest_prediction: FarmRiskPrediction | None = None,
) -> dict:
    return {
        "id": str(schedule.id),
        "farm_profile_id": str(schedule.farm_profile_id),
        "plot_id": str(schedule.plot_id) if schedule.plot_id else None,
        "crop_season_id": str(schedule.crop_season_id) if schedule.crop_season_id else None,
        "crop": schedule.crop,
        "province": schedule.province,
        "reminder_type": schedule.reminder_type,
        "frequency_hours": schedule.frequency_hours,
        "notification_scope": schedule.notification_scope,
        "status": schedule.status,
        "consent_granted_at": schedule.consent_granted_at,
        "next_run_at": schedule.next_run_at,
        "last_run_at": schedule.last_run_at,
        "last_error_code": schedule.last_error_code,
        "latest_prediction": _prediction_payload(latest_prediction),
    }


def _season_payload(season: CropSeason) -> dict:
    return {
        "id": str(season.id),
        "plot_id": str(season.plot_id),
        "crop": season.crop,
        "variety": season.variety,
        "growth_stage": season.growth_stage,
        "planted_on": season.planted_on,
        "expected_harvest_on": season.expected_harvest_on,
        "status": season.status,
        "ended_at": season.ended_at,
        "created_at": season.created_at,
        "updated_at": season.updated_at,
    }


def _plot_payload(plot: FarmPlot, seasons: list[CropSeason] | None = None) -> dict:
    return {
        "id": str(plot.id),
        "farm_profile_id": str(plot.farm_profile_id),
        "name": plot.name,
        "area_ha": plot.area_ha,
        "location_note": plot.location_note,
        "status": plot.status,
        "created_at": plot.created_at,
        "updated_at": plot.updated_at,
        "seasons": [_season_payload(item) for item in seasons or []],
    }


def _validate_season_dates(planted_on: date | None, expected_harvest_on: date | None) -> None:
    if planted_on and expected_harvest_on and expected_harvest_on < planted_on:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Expected harvest date cannot be before planting date",
        )


@router.get("/farm-profile")
async def get_farm_profile(db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    profile = (await db.execute(select(FarmProfile).where(FarmProfile.user_id == current_user["id"]))).scalar_one_or_none()
    return _profile_payload(profile) if profile else None


@router.put("/farm-profile")
async def upsert_farm_profile(req: FarmProfileRequest, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    profile = (await db.execute(select(FarmProfile).where(FarmProfile.user_id == current_user["id"]))).scalar_one_or_none()
    if profile is None:
        profile = FarmProfile(user_id=current_user["id"], **req.model_dump())
        db.add(profile)
    else:
        for key, value in req.model_dump().items():
            setattr(profile, key, value)
    await db.commit()
    await db.refresh(profile)
    return _profile_payload(profile)


@router.get("/plots")
async def list_farm_plots(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    plots = (
        await db.execute(
            select(FarmPlot)
            .where(
                FarmPlot.user_id == current_user["id"],
                FarmPlot.status != "archived",
            )
            .order_by(FarmPlot.created_at.asc())
        )
    ).scalars().all()
    if not plots:
        return []
    seasons = (
        await db.execute(
            select(CropSeason)
            .where(
                CropSeason.user_id == current_user["id"],
                CropSeason.plot_id.in_([item.id for item in plots]),
            )
            .order_by(CropSeason.created_at.desc())
        )
    ).scalars().all()
    by_plot: dict[str, list[CropSeason]] = {}
    for season in seasons:
        by_plot.setdefault(str(season.plot_id), []).append(season)
    return [_plot_payload(item, by_plot.get(str(item.id), [])) for item in plots]


@router.post("/plots", status_code=status.HTTP_201_CREATED)
async def create_farm_plot(
    req: FarmPlotCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    name = req.name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Plot name is required",
        )
    profile = (
        await db.execute(
            select(FarmProfile).where(FarmProfile.user_id == current_user["id"])
        )
    ).scalar_one_or_none()
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Farm profile is required before creating a plot",
        )
    now = local_now_naive()
    plot = FarmPlot(
        user_id=current_user["id"],
        farm_profile_id=profile.id,
        name=name,
        area_ha=req.area_ha,
        location_note=(req.location_note.strip() or None) if req.location_note else None,
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.add(plot)
    await db.commit()
    await db.refresh(plot)
    return _plot_payload(plot)


@router.patch("/plots/{plot_id}")
async def update_farm_plot(
    plot_id: str,
    req: FarmPlotUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    plot = (
        await db.execute(
            select(FarmPlot).where(
                FarmPlot.id == plot_id,
                FarmPlot.user_id == current_user["id"],
                FarmPlot.status != "archived",
            )
        )
    ).scalar_one_or_none()
    if plot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plot not found")
    updates = req.model_dump(exclude_unset=True)
    for field in ("name", "area_ha", "location_note"):
        if field in updates:
            value = updates[field]
            if isinstance(value, str):
                value = value.strip() or None
            setattr(plot, field, value)
    if not plot.name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Plot name is required",
        )
    plot.updated_at = local_now_naive()
    await db.commit()
    await db.refresh(plot)
    return _plot_payload(plot)


@router.delete("/plots/{plot_id}")
async def archive_farm_plot(
    plot_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    plot = (
        await db.execute(
            select(FarmPlot).where(
                FarmPlot.id == plot_id,
                FarmPlot.user_id == current_user["id"],
                FarmPlot.status != "archived",
            )
        )
    ).scalar_one_or_none()
    if plot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plot not found")
    active_season = (
        await db.execute(
            select(CropSeason).where(
                CropSeason.plot_id == plot.id,
                CropSeason.user_id == current_user["id"],
                CropSeason.status.in_(("planned", "active")),
            )
        )
    ).scalar_one_or_none()
    schedule = (
        await db.execute(
            select(FarmMonitoringSchedule).where(
                FarmMonitoringSchedule.plot_id == plot.id,
                FarmMonitoringSchedule.user_id == current_user["id"],
                FarmMonitoringSchedule.status.in_(("active", "paused")),
            )
        )
    ).scalar_one_or_none()
    if active_season is not None or schedule is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="End unfinished seasons and delete their monitoring schedules first",
        )
    plot.status = "archived"
    plot.updated_at = local_now_naive()
    await db.commit()
    return {"status": "archived"}


@router.post("/plots/{plot_id}/seasons", status_code=status.HTTP_201_CREATED)
async def create_crop_season(
    plot_id: str,
    req: CropSeasonCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _validate_season_dates(req.planted_on, req.expected_harvest_on)
    crop = req.crop.strip()
    if not crop:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Crop name is required",
        )
    plot = (
        await db.execute(
            select(FarmPlot).where(
                FarmPlot.id == plot_id,
                FarmPlot.user_id == current_user["id"],
                FarmPlot.status == "active",
            )
        )
    ).scalar_one_or_none()
    if plot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plot not found")
    if req.status == "active":
        active = (
            await db.execute(
                select(CropSeason).where(
                    CropSeason.plot_id == plot.id,
                    CropSeason.user_id == current_user["id"],
                    CropSeason.status == "active",
                )
            )
        ).scalar_one_or_none()
        if active is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The plot already has an active crop season",
            )
    now = local_now_naive()
    season = CropSeason(
        user_id=current_user["id"],
        plot_id=plot.id,
        crop=crop,
        variety=req.variety.strip() if req.variety else None,
        growth_stage=req.growth_stage.strip() if req.growth_stage else None,
        planted_on=req.planted_on,
        expected_harvest_on=req.expected_harvest_on,
        status=req.status,
        created_at=now,
        updated_at=now,
    )
    db.add(season)
    await db.commit()
    await db.refresh(season)
    return _season_payload(season)


@router.patch("/seasons/{season_id}")
async def update_crop_season(
    season_id: str,
    req: CropSeasonUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    season = (
        await db.execute(
            select(CropSeason).where(
                CropSeason.id == season_id,
                CropSeason.user_id == current_user["id"],
            )
        )
    ).scalar_one_or_none()
    if season is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crop season not found")
    updates = req.model_dump(exclude_unset=True)
    if "crop" in updates and not updates["crop"].strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Crop name is required",
        )
    planted_on = updates.get("planted_on", season.planted_on)
    harvest_on = updates.get("expected_harvest_on", season.expected_harvest_on)
    _validate_season_dates(planted_on, harvest_on)
    if updates.get("status") == "active" and season.status != "active":
        active = (
            await db.execute(
                select(CropSeason).where(
                    CropSeason.plot_id == season.plot_id,
                    CropSeason.user_id == current_user["id"],
                    CropSeason.status == "active",
                    CropSeason.id != season.id,
                )
            )
        ).scalar_one_or_none()
        if active is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The plot already has an active crop season",
            )
    for field in (
        "crop",
        "variety",
        "growth_stage",
        "planted_on",
        "expected_harvest_on",
        "status",
    ):
        if field in updates:
            value = updates[field]
            if isinstance(value, str):
                value = value.strip() or None
            setattr(season, field, value)
    now = local_now_naive()
    # A crop change invalidates the schedule's selected policy. Pause it until
    # the owner explicitly resumes and the policy metadata is refreshed.
    should_pause_monitoring = season.status != "active" or "crop" in updates
    if season.status in ("completed", "cancelled"):
        season.ended_at = now
    elif season.status == "active":
        season.ended_at = None
    if should_pause_monitoring:
        schedules = (
            await db.execute(
                select(FarmMonitoringSchedule).where(
                    FarmMonitoringSchedule.crop_season_id == season.id,
                    FarmMonitoringSchedule.user_id == current_user["id"],
                    FarmMonitoringSchedule.status == "active",
                )
            )
        ).scalars().all()
        for schedule in schedules:
            schedule.status = "paused"
            schedule.next_run_at = None
            schedule.updated_at = now
    season.updated_at = now
    await db.commit()
    await db.refresh(season)
    return _season_payload(season)


@router.delete("/seasons/{season_id}")
async def cancel_crop_season(
    season_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    season = (
        await db.execute(
            select(CropSeason).where(
                CropSeason.id == season_id,
                CropSeason.user_id == current_user["id"],
            )
        )
    ).scalar_one_or_none()
    if season is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crop season not found")
    schedule = (
        await db.execute(
            select(FarmMonitoringSchedule).where(
                FarmMonitoringSchedule.crop_season_id == season.id,
                FarmMonitoringSchedule.user_id == current_user["id"],
                FarmMonitoringSchedule.status.in_(("active", "paused")),
            )
        )
    ).scalar_one_or_none()
    if schedule is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Delete the monitoring schedule before deleting this crop season",
        )
    season.status = "cancelled"
    season.ended_at = local_now_naive()
    season.updated_at = season.ended_at
    await db.commit()
    return {"status": "cancelled"}


@router.get("/tasks")
async def list_tasks(db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    tasks = (await db.execute(select(FarmTask).where(FarmTask.user_id == current_user["id"]).order_by(FarmTask.due_at.asc()))).scalars().all()
    return [{"id": str(task.id), "title": task.title, "description": task.description, "due_at": task.due_at, "status": task.status} for task in tasks]


@router.patch("/tasks/{task_id}")
async def update_task(task_id: str, req: TaskUpdateRequest, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    task = (await db.execute(select(FarmTask).where(FarmTask.id == task_id, FarmTask.user_id == current_user["id"]))).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    updates = req.model_dump(exclude_unset=True)
    for field in ("title", "description", "due_at"):
        if field in updates:
            setattr(task, field, updates[field])
    if "status" in updates:
        task.status = updates["status"]
        task.completed_at = datetime.utcnow() if task.status == "completed" else None
    await db.commit()
    await db.refresh(task)
    return {"id": str(task.id), "title": task.title, "description": task.description, "due_at": task.due_at, "status": task.status}


@router.delete("/tasks/{task_id}", status_code=status.HTTP_200_OK)
async def delete_task(task_id: str, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    task = (await db.execute(select(FarmTask).where(FarmTask.id == task_id, FarmTask.user_id == current_user["id"]))).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    await db.delete(task)
    await db.commit()
    return {"status": "deleted"}


@router.get("/monitoring-schedules")
async def list_monitoring_schedules(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    schedules = (
        await db.execute(
            select(FarmMonitoringSchedule)
            .where(
                FarmMonitoringSchedule.user_id == current_user["id"],
                FarmMonitoringSchedule.status != "deleted",
            )
            .order_by(FarmMonitoringSchedule.created_at.desc())
        )
    ).scalars().all()
    if not schedules:
        return []
    predictions = (
        await db.execute(
            select(FarmRiskPrediction)
            .where(
                FarmRiskPrediction.user_id == current_user["id"],
                FarmRiskPrediction.schedule_id.in_([item.id for item in schedules]),
            )
            .order_by(FarmRiskPrediction.created_at.desc())
        )
    ).scalars().all()
    latest_by_schedule: dict[str, FarmRiskPrediction] = {}
    for prediction in predictions:
        latest_by_schedule.setdefault(str(prediction.schedule_id), prediction)
    return [
        _schedule_payload(item, latest_by_schedule.get(str(item.id)))
        for item in schedules
    ]


@router.post("/monitoring-schedules", status_code=status.HTTP_201_CREATED)
async def create_monitoring_schedule(
    req: MonitoringScheduleCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if not req.consent:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Explicit monitoring consent is required",
        )
    profile = (
        await db.execute(
            select(FarmProfile).where(FarmProfile.user_id == current_user["id"])
        )
    ).scalar_one_or_none()
    if profile is None or not profile.province:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Farm profile province is required",
        )
    if not is_supported_region(profile.province):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A named Vietnamese province is required",
        )
    season = (
        await db.execute(
            select(CropSeason).where(
                CropSeason.id == req.crop_season_id,
                CropSeason.user_id == current_user["id"],
                CropSeason.status == "active",
            )
        )
    ).scalar_one_or_none()
    if season is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="An owned active crop season is required",
        )
    plot = (
        await db.execute(
            select(FarmPlot).where(
                FarmPlot.id == season.plot_id,
                FarmPlot.user_id == current_user["id"],
                FarmPlot.farm_profile_id == profile.id,
                FarmPlot.status == "active",
            )
        )
    ).scalar_one_or_none()
    if plot is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The crop season does not belong to an active plot",
        )
    if not is_supported_crop(season.crop):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A named crop is required for weather monitoring",
        )
    policy = resolve_monitoring_policy(season.crop)
    existing = (
        await db.execute(
            select(FarmMonitoringSchedule).where(
                FarmMonitoringSchedule.user_id == current_user["id"],
                FarmMonitoringSchedule.crop_season_id == season.id,
                FarmMonitoringSchedule.status.in_(("active", "paused")),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A monitoring schedule already exists for this crop season",
        )
    now = local_now_naive()
    schedule = FarmMonitoringSchedule(
        user_id=current_user["id"],
        farm_profile_id=profile.id,
        plot_id=plot.id,
        crop_season_id=season.id,
        crop=season.crop.strip(),
        province=profile.province.strip(),
        reminder_type=policy.reminder_type,
        frequency_hours=req.frequency_hours,
        notification_scope=req.notification_scope,
        status="active",
        consent_granted_at=now,
        next_run_at=now,
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    return _schedule_payload(schedule)


@router.patch("/monitoring-schedules/{schedule_id}")
async def update_monitoring_schedule(
    schedule_id: str,
    req: MonitoringScheduleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    schedule = (
        await db.execute(
            select(FarmMonitoringSchedule).where(
                FarmMonitoringSchedule.id == schedule_id,
                FarmMonitoringSchedule.user_id == current_user["id"],
                FarmMonitoringSchedule.status != "deleted",
            )
        )
    ).scalar_one_or_none()
    if schedule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitoring schedule not found")
    updates = req.model_dump(exclude_unset=True)
    for field in ("frequency_hours", "notification_scope"):
        if field in updates:
            setattr(schedule, field, updates[field])
    if "status" in updates:
        if updates["status"] == "active":
            if schedule.crop_season_id is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Attach an active crop season before resuming this schedule",
                )
            season = (
                await db.execute(
                    select(CropSeason).where(
                        CropSeason.id == schedule.crop_season_id,
                        CropSeason.user_id == current_user["id"],
                        CropSeason.status == "active",
                    )
                )
            ).scalar_one_or_none()
            if season is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="The crop season is no longer active",
                )
            if not is_supported_crop(season.crop):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="The crop season needs a named crop",
                )
            policy = resolve_monitoring_policy(season.crop)
            schedule.crop = season.crop.strip()
            schedule.reminder_type = policy.reminder_type
        schedule.status = updates["status"]
        schedule.next_run_at = local_now_naive() if schedule.status == "active" else None
    schedule.updated_at = local_now_naive()
    await db.commit()
    await db.refresh(schedule)
    return _schedule_payload(schedule)


@router.delete("/monitoring-schedules/{schedule_id}")
async def delete_monitoring_schedule(
    schedule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    schedule = (
        await db.execute(
            select(FarmMonitoringSchedule).where(
                FarmMonitoringSchedule.id == schedule_id,
                FarmMonitoringSchedule.user_id == current_user["id"],
                FarmMonitoringSchedule.status != "deleted",
            )
        )
    ).scalar_one_or_none()
    if schedule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitoring schedule not found")
    schedule.status = "deleted"
    schedule.next_run_at = None
    schedule.updated_at = local_now_naive()
    await db.commit()
    return {"status": "deleted"}


@router.get("/notifications")
async def list_notifications(db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    notifications = (await db.execute(select(Notification).where(Notification.user_id == current_user["id"]).order_by(Notification.created_at.desc()).limit(50))).scalars().all()
    recommendations = []
    if notifications:
        recommendations = (
            await db.execute(
                select(FarmRecommendation).where(
                    FarmRecommendation.user_id == current_user["id"],
                    FarmRecommendation.notification_id.in_([item.id for item in notifications]),
                )
            )
        ).scalars().all()
    by_notification = {str(item.notification_id): item for item in recommendations}
    return [
        {
            "id": str(item.id),
            "kind": item.kind,
            "title": item.title,
            "body": item.body,
            "created_at": item.created_at,
            "read_at": item.read_at,
            "recommendation": (
                {
                    "id": str(recommendation.id),
                    "status": recommendation.status,
                    "pending_action_id": str(recommendation.pending_action_id),
                    "expires_at": recommendation.expires_at,
                }
                if (recommendation := by_notification.get(str(item.id))) is not None
                and recommendation.pending_action_id is not None
                else None
            ),
        }
        for item in notifications
    ]


@router.post("/device-tokens")
async def register_device_token(req: DeviceTokenRequest, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    token = (await db.execute(select(DeviceToken).where(DeviceToken.token == req.token))).scalar_one_or_none()
    if token is None:
        token = DeviceToken(user_id=current_user["id"], **req.model_dump())
        db.add(token)
    elif str(token.user_id) != str(current_user["id"]):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Device token is already registered")
    else:
        token.platform, token.active = req.platform, True
    await db.commit()
    return {"status": "registered"}


@router.delete("/device-tokens/{token}")
async def revoke_device_token(token: str, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    device = (await db.execute(select(DeviceToken).where(DeviceToken.token == token, DeviceToken.user_id == current_user["id"]))).scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device token not found")
    device.active = False
    await db.commit()
    return {"status": "revoked"}


@router.post("/actions/{action_id}/confirm")
async def confirm_action(action_id: str, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    action = (
        await db.execute(
            select(PendingAction)
            .where(
                PendingAction.id == action_id,
                PendingAction.user_id == current_user["id"],
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if action is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending action not found")
    recommendation = (
        await db.execute(
            select(FarmRecommendation).where(
                FarmRecommendation.pending_action_id == action.id,
                FarmRecommendation.user_id == current_user["id"],
            )
        )
    ).scalar_one_or_none()
    if action.status == "confirmed":
        return {
            "status": "confirmed",
            "action_type": action.action_type,
            "record_id": str(recommendation.task_id) if recommendation and recommendation.task_id else None,
        }
    if action.status != "pending":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending action not found")
    if action.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        action.status = "expired"
        if recommendation is not None:
            recommendation.status = "expired"
            recommendation.resolved_at = local_now_naive()
        await db.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Pending action has expired")
    payload = action.payload
    if action.action_type == "create_task":
        record = FarmTask(user_id=current_user["id"], title=payload["title"], description=payload.get("description"), due_at=datetime.fromisoformat(payload["due_at"]) if payload.get("due_at") else None)
    elif action.action_type == "create_log":
        record = FarmLog(user_id=current_user["id"], title=payload["title"], content=payload["content"])
    else:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported action type")
    db.add(record)
    await db.flush()
    action.status = "confirmed"
    if recommendation is not None:
        recommendation.status = "accepted"
        recommendation.task_id = record.id
        recommendation.resolved_at = local_now_naive()
    await db.commit()
    return {"status": "confirmed", "action_type": action.action_type, "record_id": str(record.id)}


@router.post("/actions/{action_id}/cancel")
async def cancel_action(action_id: str, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    action = (await db.execute(select(PendingAction).where(PendingAction.id == action_id, PendingAction.user_id == current_user["id"]))).scalar_one_or_none()
    if action is None or action.status != "pending":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending action not found")
    action.status = "cancelled"
    recommendation = (
        await db.execute(
            select(FarmRecommendation).where(
                FarmRecommendation.pending_action_id == action.id,
                FarmRecommendation.user_id == current_user["id"],
            )
        )
    ).scalar_one_or_none()
    if recommendation is not None:
        recommendation.status = "dismissed"
        recommendation.resolved_at = local_now_naive()
    await db.commit()
    return {"status": "cancelled"}
