from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-only runtime configuration; secrets stay masked in repr/logs."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "InfraSentinel AI"
    app_version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    infrasentinel_env: Literal["development", "test", "production"] = "development"
    infrasentinel_secret_key: SecretStr = SecretStr("development-only-change-me")

    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://infrasentinel:infrasentinel@127.0.0.1:5432/infrasentinel"
    )
    redis_url: SecretStr = SecretStr("redis://127.0.0.1:6379/0")
    milvus_host: str = "127.0.0.1"
    milvus_port: int = Field(default=19530, ge=1, le=65535)

    storage_root: Path = Path("runtime/storage")
    storage_warning_gb: int = Field(default=900, ge=1)

    @model_validator(mode="after")
    def reject_unsafe_production_defaults(self) -> Settings:
        secret = self.infrasentinel_secret_key.get_secret_value()
        if self.infrasentinel_env == "production":
            if secret == "development-only-change-me" or len(secret) < 32:
                raise ValueError("production requires INFRASENTINEL_SECRET_KEY with 32+ characters")
            database_url = self.database_url.get_secret_value()
            redis_url = self.redis_url.get_secret_value()
            if "infrasentinel:infrasentinel@" in database_url:
                raise ValueError("production requires a non-default database password")
            if redis_url == "redis://127.0.0.1:6379/0":
                raise ValueError("production requires Redis authentication")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
