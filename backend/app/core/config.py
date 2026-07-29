from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Cấu hình trung tâm. Mọi service (DB, Redis, Qdrant) đọc từ đây,
    không hardcode connection string ở bất kỳ file nào khác.
    """

    app_name: str = "AgriMind AI"
    environment: str = "development"

    database_url: str = "postgresql+asyncpg://agrimind:agrimind_dev_password@localhost:5432/agrimind"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_base_url: str = "https://cloud.langfuse.com"
    google_api_key: str = ""
    openweather_api_key: str = ""
    embedding_service_url: str = "http://localhost:8001"
    supabase_url: str = ""
    supabase_secret_key: str = ""
    supabase_bucket_name: str = "agrimind-documents"
    supabase_publishable_key: str = ""
    supabase_jwks_url: str = ""
    mcp_weather_url: str = "http://localhost:8002/mcp"
    # Model routing - điền API key thật qua .env, không commit vào git
    llm_provider_strong: str = "gpt-5"      # dùng cho generate/reflection
    llm_provider_fast: str = "gemini-flash"  # dùng cho planner/guardrail

    class Config:
        env_file = ".env"


settings = Settings()
