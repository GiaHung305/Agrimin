from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.db import get_db
from app.repository.models import DeviceToken, FarmLog, FarmProfile, FarmTask, Notification, PendingAction

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


def _profile_payload(profile: FarmProfile) -> dict:
    return {key: getattr(profile, key) for key in ("id", "name", "province", "crop", "area_ha", "farming_style")}


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


@router.get("/notifications")
async def list_notifications(db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    notifications = (await db.execute(select(Notification).where(Notification.user_id == current_user["id"]).order_by(Notification.created_at.desc()).limit(50))).scalars().all()
    return [{"id": str(item.id), "kind": item.kind, "title": item.title, "body": item.body, "created_at": item.created_at, "read_at": item.read_at} for item in notifications]


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
    action = (await db.execute(select(PendingAction).where(PendingAction.id == action_id, PendingAction.user_id == current_user["id"]))).scalar_one_or_none()
    if action is None or action.status != "pending":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending action not found")
    if action.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        action.status = "expired"
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
    action.status = "confirmed"
    await db.commit()
    return {"status": "confirmed", "action_type": action.action_type, "record_id": str(record.id)}


@router.post("/actions/{action_id}/cancel")
async def cancel_action(action_id: str, db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)):
    action = (await db.execute(select(PendingAction).where(PendingAction.id == action_id, PendingAction.user_id == current_user["id"]))).scalar_one_or_none()
    if action is None or action.status != "pending":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending action not found")
    action.status = "cancelled"
    await db.commit()
    return {"status": "cancelled"}
