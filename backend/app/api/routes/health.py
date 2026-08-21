from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.redis_client import check_redis_connection
from app.core.qdrant_client import check_qdrant_connection

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """
    Kiểm tra kết nối tới cả 3 hạ tầng cùng lúc.
    Mục tiêu Sprint 1: endpoint này phải trả về "ok" cho cả 3 trước khi
    chuyển sang Sprint 2 (LangGraph core).
    """
    result = {"postgres": "down", "redis": "down", "qdrant": "down"}

    try:
        await db.execute(text("SELECT 1"))
        result["postgres"] = "ok"
    except Exception as e:
        result["postgres"] = f"error: {e}"

    result["redis"] = "ok" if await check_redis_connection() else "down"
    result["qdrant"] = "ok" if await check_qdrant_connection() else "down"

    overall = "ok" if all(v == "ok" for v in result.values()) else "degraded"

    return {"status": overall, "services": result}
