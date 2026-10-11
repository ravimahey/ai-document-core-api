from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings.

    Precedence (highest first): real environment variables > .env file > defaults here.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Document Analysis Using AI"
    app_version: str = "1.0.0"
    environment: Literal["local", "test", "staging", "production"] = "local"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    api_v1_prefix: str = "/api/v1"

    database_url: str = "sqlite:///./data/app.db"
    db_echo: bool = False
    jwt_algorithm: Literal["RS256", "ES256"] = "RS256"
    jwt_private_key: str = Field(default="")
    jwt_public_key: str = Field(default="")
    jwt_key_id: str = "user"
    jwt_issuer: str = "user"
    jwt_audience: str = "user"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # OTP Configuration
    otp_expire_minutes: int = 5
    otp_length: int = 6
    otp_max_attempts: int = 5
    otp_resend_cooldown_seconds: int = 60
    otp_max_requests_per_hour: int = 10
    otp_secret_key: str = Field(
        default="default-insecure-otp-secret-key-change-in-production"
    )

    # Email Service Configuration
    email_provider: Literal["console", "smtp", "mock"] = "console"
    smtp_host: str = "smtp.example.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "noreply@documentanalysis.ai"
    smtp_use_tls: bool = True

    # Chatbot & LLM Configuration (OpenAI / LangChain)
    openai_api_key: str = Field(default="")
    openai_model: str = "gpt-4.1-nano"
    openai_temperature: float = 0.7
    openai_max_output_tokens: int = 2048
    chat_max_input_characters: int = 4000
    chat_history_message_limit: int = 20
    chat_request_timeout_seconds: float = 30.0
    chat_system_prompt: str = (
        "You are a helpful, respectful, and concise AI assistant."
    )

    # Object Storage Configuration (MinIO / Amazon S3 / Local)
    object_storage_provider: Literal["minio", "s3", "local"] = "minio"
    minio_endpoint_url: str = "http://localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket_name: str = "documents"
    minio_region: str = "us-east-1"
    minio_secure: bool = False

    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_region: str = "us-east-1"
    aws_s3_bucket_name: str = "documents"

    local_storage_path: str = "./data/storage"

    # Celery & Redis Configuration
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    celery_task_always_eager: bool = False

    # Document Ingestion, Chunking & Embeddings
    max_upload_size_bytes: int = 25 * 1024 * 1024  # 25 MB
    embedding_model: str = "text-embedding-3-small"
    chunk_size: int = 1000
    chunk_overlap: int = 150
    faiss_index_dir: str = "./data/faiss_indexes"


@lru_cache
def get_settings() -> Settings:
    """Cached so the .env file is parsed once per process."""
    return Settings()
