import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt

from app.core.config import settings

security = HTTPBearer()
_jwks_cache = None


async def get_jwks():
    global _jwks_cache
    if _jwks_cache is None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(settings.supabase_jwks_url)
            response.raise_for_status()
            _jwks_cache = response.json()
    return _jwks_cache


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Validate a Supabase JWT and return the user identity used by the API."""
    try:
        payload = jwt.decode(
            credentials.credentials,
            await get_jwks(),
            algorithms=["RS256", "ES256"],
            audience="authenticated",
        )
        return {"id": payload["sub"], "email": payload.get("email", "")}
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
        )


def _configured_admins() -> tuple[set[str], set[str]]:
    user_ids = {user_id.strip() for user_id in settings.admin_user_ids.split(",") if user_id.strip()}
    emails = {email.strip().casefold() for email in settings.admin_emails.split(",") if email.strip()}
    return user_ids, emails


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Allow document management only to explicitly configured administrators."""
    admin_ids, admin_emails = _configured_admins()
    is_configured_admin = (
        current_user["id"] in admin_ids
        or current_user.get("email", "").casefold() in admin_emails
    )
    if is_configured_admin or (settings.environment == "development" and not admin_ids and not admin_emails):
        return current_user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Document management requires an administrator account",
    )
