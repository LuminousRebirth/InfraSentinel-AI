from __future__ import annotations

import pytest
from pydantic import ValidationError

from infrasentinel.config import Settings


def test_secret_is_masked_in_settings_repr() -> None:
    settings = Settings(_env_file=None, infrasentinel_secret_key="a-very-secret-value")
    assert "a-very-secret-value" not in repr(settings)


def test_production_rejects_short_secret() -> None:
    with pytest.raises(ValidationError, match="32\\+ characters"):
        Settings(
            _env_file=None,
            infrasentinel_env="production",
            infrasentinel_secret_key="short",
        )


def test_production_accepts_strong_secret() -> None:
    settings = Settings(
        _env_file=None,
        infrasentinel_env="production",
        infrasentinel_secret_key="x" * 32,
        database_url="postgresql+psycopg://app:strong-password@db:5432/app",
        redis_url="redis://:strong-password@redis:6379/0",
    )
    assert settings.infrasentinel_env == "production"


def test_production_rejects_default_database_password() -> None:
    with pytest.raises(ValidationError, match="non-default database password"):
        Settings(
            _env_file=None,
            infrasentinel_env="production",
            infrasentinel_secret_key="x" * 32,
            database_url=(
                "postgresql+psycopg://infrasentinel:infrasentinel@127.0.0.1:5432/infrasentinel"
            ),
            redis_url="redis://:strong-password@redis:6379/0",
        )


def test_vision_settings_are_bounded() -> None:
    settings = Settings(_env_file=None)
    assert settings.infrasentinel_vision_workers == 2
    assert settings.infrasentinel_image_max_mb == 50
    assert settings.infrasentinel_video_max_gb == 5
    assert settings.infrasentinel_video_max_seconds == 7200

    with pytest.raises(ValidationError):
        Settings(_env_file=None, infrasentinel_image_max_mb=51)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, infrasentinel_task_lease_seconds=5)
