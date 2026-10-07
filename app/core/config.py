from functools import lru_cache
from typing import Literal

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

    database_url: str = "sqlite:///./db/todo.db"
    db_echo: bool = False
    jwt_algorithm: Literal["RS256", "ES256"] = "RS256"   # symmetric HS* is deliberately not allowed
    jwt_private_key: str      # no default: fail fast if missing
    jwt_public_key: str
    jwt_key_id: str = "user"
    jwt_issuer: str = "user"
    jwt_audience: str = "user, ai"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7


@lru_cache
def get_settings() -> Settings:
    """Cached so the .env file is parsed once per process."""
    return Settings()
