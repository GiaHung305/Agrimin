from fastapi import APIRouter, Depends

from app.core.auth import (
    get_current_user,
    permissions_for_user,
    role_for_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/session")
async def get_session(current_user: dict = Depends(get_current_user)) -> dict:
    """Return the server-authoritative role and permissions for the session."""
    role = role_for_user(current_user)
    return {
        "user_id": current_user["id"],
        "email": current_user.get("email", ""),
        "role": role.value,
        "permissions": [
            permission.value for permission in permissions_for_user(current_user)
        ],
    }
