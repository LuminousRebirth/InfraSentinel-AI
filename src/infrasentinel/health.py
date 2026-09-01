from __future__ import annotations

import socket
from collections.abc import Callable

import redis
from pydantic import BaseModel
from sqlalchemy import text

from .config import Settings, get_settings
from .database import get_engine
from .storage import StorageStatus, ensure_storage


class DependencyHealth(BaseModel):
    status: str
    detail: str | None = None


class ReadinessResponse(BaseModel):
    status: str
    dependencies: dict[str, DependencyHealth]


def _result(check: Callable[[], None]) -> DependencyHealth:
    try:
        check()
    except Exception as exc:
        return DependencyHealth(status="unavailable", detail=type(exc).__name__)
    return DependencyHealth(status="ok")


def _storage_result(status: StorageStatus, warning_gb: int) -> DependencyHealth:
    if status.warning:
        return DependencyHealth(
            status="warning",
            detail=f"{status.free_gb} GB free; warning threshold is {warning_gb} GB",
        )
    return DependencyHealth(status="ok")


def readiness(settings: Settings | None = None) -> ReadinessResponse:
    settings = settings or get_settings()

    def postgres_check() -> None:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))

    def redis_check() -> None:
        client = redis.Redis.from_url(
            settings.redis_url.get_secret_value(), socket_connect_timeout=2, socket_timeout=2
        )
        try:
            client.ping()
        finally:
            client.close()

    def milvus_check() -> None:
        with socket.create_connection((settings.milvus_host, settings.milvus_port), timeout=2):
            pass

    dependencies = {
        "postgresql": _result(postgres_check),
        "redis": _result(redis_check),
        "milvus": _result(milvus_check),
    }
    try:
        storage_status = ensure_storage(settings.storage_root, settings.storage_warning_gb)
        dependencies["storage"] = _storage_result(storage_status, settings.storage_warning_gb)
    except Exception as exc:
        dependencies["storage"] = DependencyHealth(status="unavailable", detail=type(exc).__name__)

    status = (
        "degraded"
        if any(item.status == "unavailable" for item in dependencies.values())
        else "ready"
    )
    return ReadinessResponse(status=status, dependencies=dependencies)
