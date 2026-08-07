from pydantic_settings import BaseSettings, SettingsConfigDict


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
    # Stable champion models. Keep provider model names out of workflow nodes
    # so a challenger can be evaluated without rewriting graph logic.
    model_planner: str = "gemini-3.1-flash-lite"
    model_reflection: str = "gemini-3.1-flash-lite"
    model_generation: str = "gemini-3.5-flash"
    model_memory: str = "gemini-3.1-flash-lite"
    model_request_timeout_seconds: float = 45.0
    ai_policy_version: str = "safety-v2"
    prompt_bundle_version: str = "prompts-v2"
    evidence_schema_version: str = "evidence-v2"
    knowledge_base_version: str = "kb-v1"
    # Deep Research uses Gemini Google Search grounding. It is opt-in per chat
    # request because each search query can incur a provider charge.
    deep_research_enabled: bool = False
    deep_research_model: str = "gemini-3.5-flash"
    deep_research_max_sources: int = 6
    openweather_api_key: str = ""
    embedding_service_url: str = "http://localhost:8001"
    supabase_url: str = ""
    supabase_secret_key: str = ""
    supabase_bucket_name: str = "agrimind-documents"
    supabase_publishable_key: str = ""
    supabase_jwks_url: str = ""
    eval_user_email: str = ""
    eval_user_password: str = ""
    eval_api_url: str = "http://localhost:8000/api/v1/chat/stream"
    eval_dataset_version: str = "v1"
    eval_judge_model: str = "gemini-3.1-flash-lite"
    eval_request_delay_seconds: float = 7.0
    mcp_weather_url: str = "http://localhost:8002/mcp"
    mcp_request_timeout_seconds: float = 10.0
    firebase_credentials_path: str = ""
    # Rebuilding BM25 requires loading and tokenising every active chunk. Keep
    # the in-process index briefly, and invalidate it immediately on writes.
    bm25_index_ttl_seconds: int = 300
    rerank_min_confidence: float = 0.10
    retrieval_excluded_sources: str = "test,mock_source"
    rrf_dense_weight: float = 1.0
    rrf_sparse_weight: float = 1.15
    cors_origins: str = ""
    admin_user_ids: str = ""
    admin_emails: str = ""
    max_upload_bytes: int = 20 * 1024 * 1024
    max_chat_image_bytes: int = 4 * 1024 * 1024
    max_chat_image_pixels: int = 16_000_000
    min_chat_image_dimension: int = 256
    vision_analysis_enabled: bool = False
    vision_request_timeout_seconds: float = 30.0
    vision_observation_schema_version: str = "visual-observation-v1"
    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
