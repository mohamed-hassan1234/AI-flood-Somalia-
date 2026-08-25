from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    secret_key: str = Field(default="development-secret-change-me-123456789", min_length=32)
    database_url: str = "sqlite+pysqlite:///./somalia_ai_dev.db"
    redis_url: str = "redis://localhost:6379/0"
    rate_limit_backend: Literal["local", "redis"] = "local"
    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "minio"
    s3_secret_key: str = "development-only-change-me"
    s3_bucket: str = "somalia-ai"
    cors_origins: list[str] = ["http://localhost:5173"]
    metrics_token: SecretStr | None = None
    auth_rate_limit_per_minute: int = Field(default=1000, ge=1, le=10000)
    public_rate_limit_per_minute: int = Field(default=120, ge=1, le=100000)
    dashboard_stale_after_hours: int = Field(default=24, ge=1, le=8760)
    notification_provider: Literal["development", "gateway"] = "development"
    notification_gateway_url: str | None = None
    notification_gateway_token: SecretStr | None = None
    notification_timeout_seconds: float = Field(default=5, ge=1, le=30)

    @model_validator(mode="after")
    def reject_unsafe_production_defaults(self) -> "Settings":
        if self.environment.lower() != "production":
            return self
        unsafe = {
            "development-secret-change-me-123456789",
            "development-only-change-me",
            "minio",
        }
        if self.secret_key in unsafe or self.s3_access_key in unsafe or self.s3_secret_key in unsafe:
            raise ValueError("Production secrets must not use development defaults")
        if "*" in self.cors_origins:
            raise ValueError("Production CORS origins must be explicit")
        if self.rate_limit_backend != "redis":
            raise ValueError("Production requires the Redis rate-limit backend")
        if self.notification_provider != "gateway":
            raise ValueError("Production requires the notification gateway provider")
        if not self.notification_gateway_url or not self.notification_gateway_url.startswith(
            "https://"
        ):
            raise ValueError("Production notification gateway must use HTTPS")
        if self.notification_gateway_token is None:
            raise ValueError("Production notification gateway token is required")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
