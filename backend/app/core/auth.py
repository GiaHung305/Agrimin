import asyncio
import time
from enum import StrEnum

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import settings

security = HTTPBearer()
_jwks_cache = None
_jwks_cached_at = 0.0
_jwks_lock = asyncio.Lock()


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


class Permission(StrEnum):
    ASSISTANT_USE = "assistant:use"
    FARM_MANAGE = "farm:manage"
    DOCUMENT_MANAGE = "document:manage"
    OPERATIONS_VIEW = "operations:view"


ROLE_PERMISSIONS: dict[UserRole, tuple[Permission, ...]] = {
    UserRole.USER: (Permission.ASSISTANT_USE, Permission.FARM_MANAGE),
    UserRole.ADMIN: tuple(Permission),
}


async def get_jwks(*, force_refresh: bool = False):
    global _jwks_cache, _jwks_cached_at
    cache_expired = (
        time.monotonic() - _jwks_cached_at
        >= settings.supabase_jwks_cache_seconds
    )
    if not force_refresh and _jwks_cache is not None and not cache_expired:
        return _jwks_cache

    async with _jwks_lock:
        cache_expired = (
            time.monotonic() - _jwks_cached_at
            >= settings.supabase_jwks_cache_seconds
        )
        if not force_refresh and _jwks_cache is not None and not cache_expired:
            return _jwks_cache
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(settings.supabase_jwks_url)
            response.raise_for_status()
            _jwks_cache = response.json()
            _jwks_cached_at = time.monotonic()
    return _jwks_cache


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Validate a Supabase JWT and return the user identity used by the API."""
    issuer = f"{settings.supabase_url.rstrip('/')}/auth/v1" if settings.supabase_url else None
    for force_refresh in (False, True):
        try:
            keys = await get_jwks(force_refresh=force_refresh)
        except httpx.HTTPError as exc:
            if not force_refresh:
                continue
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service temporarily unavailable",
            ) from exc
        try:
            payload = jwt.decode(
                credentials.credentials,
                keys,
                algorithms=["RS256", "ES256"],
                audience="authenticated",
                issuer=issuer,
                options={"verify_iss": issuer is not None},
            )
            return {"id": payload["sub"], "email": payload.get("email", "")}
        except (JWTError, KeyError, ValueError):
            if force_refresh:
                break

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired access token",
    )


def _configured_admins() -> tuple[set[str], set[str]]:
    user_ids = {user_id.strip() for user_id in settings.admin_user_ids.split(",") if user_id.strip()}
    emails = {email.strip().casefold() for email in settings.admin_emails.split(",") if email.strip()}
    return user_ids, emails


def role_for_user(current_user: dict) -> UserRole:
    admin_ids, admin_emails = _configured_admins()
    if (
        current_user["id"] in admin_ids
        or current_user.get("email", "").casefold() in admin_emails
    ):
        return UserRole.ADMIN
    return UserRole.USER


def permissions_for_user(current_user: dict) -> tuple[Permission, ...]:
    return ROLE_PERMISSIONS[role_for_user(current_user)]


def require_permission(permission: Permission):
    async def dependency(
        current_user: dict = Depends(get_current_user),
    ) -> dict:
        if permission in permissions_for_user(current_user):
            return current_user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required permission: {permission.value}",
        )

    return dependency


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Allow document management only to explicitly configured administrators."""
    if role_for_user(current_user) is UserRole.ADMIN:
        return current_user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Document management requires an administrator account",
    )
