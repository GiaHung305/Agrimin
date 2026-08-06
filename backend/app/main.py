from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from google.genai.errors import ClientError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api import assistant, chat, documents, health
from app.core.ai_service_client import close_ai_service_client
from app.core.checkpointer import close_checkpointer, init_checkpointer
from app.core.config import settings
from app.retrieval.qdrant_setup import ensure_collection_exists

app = FastAPI(title=settings.app_name)

configured_origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
allowed_origins = configured_origins or (["*"] if settings.environment == "development" else [])

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=allowed_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(assistant.router, prefix="/api/v1")

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.get("/")
async def root():
    return {"message": f"{settings.app_name} backend is running"}


@app.on_event("startup")
async def startup_event():
    await ensure_collection_exists()
    await init_checkpointer()


@app.exception_handler(ClientError)
async def gemini_quota_handler(request, exc):
    if "RESOURCE_EXHAUSTED" in str(exc):
        return JSONResponse(
            status_code=503,
            content={"detail": "The AI service is temporarily busy. Please try again shortly."},
        )
    return JSONResponse(status_code=500, content={"detail": "An unexpected service error occurred."})


@app.on_event("shutdown")
async def shutdown_event():
    await close_ai_service_client()
    await close_checkpointer()
