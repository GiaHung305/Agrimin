import asyncio
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


async def send_push(token: str, title: str, body: str) -> bool:
    """Send through FCM when credentials are configured; in-app delivery still works without it."""
    if not settings.firebase_credentials_path:
        return False
    try:
        import firebase_admin
        from firebase_admin import credentials, messaging

        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(settings.firebase_credentials_path))
        await asyncio.to_thread(
            messaging.send,
            messaging.Message(notification=messaging.Notification(title=title, body=body), token=token),
        )
        return True
    except Exception:
        logger.exception("FCM push delivery failed")
        return False
