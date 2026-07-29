import httpx

from app.core.config import settings

STORAGE_BASE_URL = f"{settings.supabase_url}/storage/v1/object"


async def upload_file(file_bytes: bytes, key: str, content_type: str) -> str:
    """
    Lưu file gốc (PDF/text) vào Supabase Storage.
    Quan trọng: key mới (sb_secret_...) phải đặt trong header 'apikey',
    KHÔNG đặt trong 'Authorization: Bearer' — vì đó không phải JWT,
    gateway sẽ cố decode như JWT và từ chối với lỗi "Invalid Compact JWS".
    """
    url = f"{STORAGE_BASE_URL}/{settings.supabase_bucket_name}/{key}"
    headers = {
        "apikey": settings.supabase_secret_key,
        "Content-Type": content_type,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, content=file_bytes)
        if response.status_code >= 400:
            print(f"[DEBUG] Supabase Storage error: {response.status_code} - {response.text}")
        response.raise_for_status()
    return key


async def download_file(key: str) -> bytes:
    url = f"{STORAGE_BASE_URL}/{settings.supabase_bucket_name}/{key}"
    headers = {"apikey": settings.supabase_secret_key}
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
    return response.content