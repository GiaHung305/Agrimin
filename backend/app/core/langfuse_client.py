import os

from langfuse.langchain import CallbackHandler

from app.core.config import settings

# SDK Langfuse mới (v3+) đọc trực tiếp từ os.environ, không nhận qua constructor nữa.
# Cần bơm giá trị từ Settings vào os.environ trước khi khởi tạo handler.
os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
os.environ.setdefault("LANGFUSE_BASE_URL", settings.langfuse_base_url)


def get_langfuse_handler() -> CallbackHandler:
    return CallbackHandler()