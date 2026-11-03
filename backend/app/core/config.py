"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "AgentGuard"
    # Production-safe default; local development can explicitly set DEBUG=true.
    debug: bool = False
    public_demo_mode: bool = False
    api_prefix: str = "/api"

    # Database
    database_url: str = "sqlite:///./agentguard.db"

    # Security
    secret_key: str = "dev-secret-key-change-in-production"
    # Admin API key MUST be set via environment variable. No default for security.
    admin_api_key: Optional[str] = None

    # CORS
    cors_origins: List[str] = ["http://localhost:5173"]

    # Pagination defaults
    default_page_size: int = 20
    max_page_size: int = 100

    # PayPal Sandbox Configuration
    paypal_client_id: Optional[str] = None
    paypal_client_secret: Optional[str] = None
    paypal_environment: str = "sandbox"  # sandbox or live

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug_marker(cls, value):
        """Treat the existing release marker as the safe non-debug mode."""
        if isinstance(value, str) and value.strip().lower() == "release":
            return False
        return value


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
