from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from google.genai.errors import ClientError

from app.core.config import settings
from app.api import health, chat, documents
from app.retrieval.qdrant_setup import ensure_collection_exists

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
app = FastAPI(title=settings.app_name)

allowed_origins = ["*"] if settings.environment == "development" else [
    "https://your-production-domain.com",  # sửa lại khi deploy thật
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")


limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.get("/")
async def root():
    return {"message": f"{settings.app_name} backend đang chạy"}


@app.on_event("startup")
async def startup_event():
    await ensure_collection_exists()

@app.exception_handler(ClientError)
async def gemini_quota_handler(request, exc):
    if "RESOURCE_EXHAUSTED" in str(exc):
        return JSONResponse(
            status_code=503,
            content={"detail": "Hệ thống đang bận (hết quota tạm thời), vui lòng thử lại sau ít phút."},
        )
    return JSONResponse(status_code=500, content={"detail": "Có lỗi xảy ra, vui lòng thử lại."})