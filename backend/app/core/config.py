from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    APP_NAME: str = "rag-services"
    APP_ENV: str = "dev"
    LOG_LEVEL: str = "INFO"
    SECRET_KEY: str = "change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6380/0"

    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION: str = "kb_chunks"

    S3_ENDPOINT: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET: str = "rag-docs"
    S3_REGION: str = "us-east-1"

    EMBEDDING_MODEL: str = "BAAI/bge-small-zh-v1.5"
    EMBEDDING_DIM: int = 512

    # Rerank (cross-encoder). Set RERANK_ENABLED=false to skip — the model is ~600MB and lazy-loaded.
    RERANK_ENABLED: bool = True
    RERANK_MODEL: str = "BAAI/bge-reranker-v2-m3"
    RERANK_TOP_K: int = 5

    # Hybrid retrieval
    HYBRID_BM25_TOP_K: int = 20
    HYBRID_VECTOR_TOP_K: int = 20
    HYBRID_RRF_K: int = 60  # constant in RRF formula

    # FAQ short-circuit
    FAQ_HIT_THRESHOLD: float = 0.85  # vector cosine threshold to short-circuit LLM

    # Semantic cache
    CACHE_ENABLED: bool = True
    CACHE_SIM_THRESHOLD: float = 0.95
    CACHE_TTL_SECONDS: int = 86400

    DASHSCOPE_API_KEY: str = "sk-REPLACE-ME"
    DASHSCOPE_BASE_URL: str = ""  # leave empty to use SDK default; intl: https://dashscope-intl.aliyuncs.com
    LLM_MODEL: str = "qwen-plus"
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: int = 800
    # Qwen3 family enables "thinking mode" by default which adds 10-30s before first token.
    # Disable for low-latency customer service use case.
    LLM_DISABLE_THINKING: bool = True

    BOOTSTRAP_ADMIN_EMAIL: str = "admin@example.com"
    BOOTSTRAP_ADMIN_PASSWORD: str = "admin123456"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
