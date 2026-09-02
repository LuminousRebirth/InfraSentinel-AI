from __future__ import annotations

import ctypes
import os
import socket
from collections.abc import Callable
from pathlib import Path

import redis
from pydantic import BaseModel
from sqlalchemy import select, text

from .config import Settings, get_settings
from .database import SessionLocal, get_engine
from .detection_models import ModelAvailability, VisionModel
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


def _pid_is_running(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    kernel32.CloseHandle(handle)
    return True


def _running_worker_count(runtime_root: Path) -> int:
    running = 0
    for pid_path in runtime_root.glob("worker-*.pid"):
        try:
            pid = int(pid_path.read_text(encoding="ascii").strip())
        except ValueError:
            continue
        if _pid_is_running(pid):
            running += 1
    return running


def _pid_file_running(pid_path: Path) -> bool:
    try:
        return _pid_is_running(int(pid_path.read_text(encoding="ascii").strip()))
    except (OSError, ValueError):
        return False


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
    runtime_root = Path("runtime")
    worker_count = _running_worker_count(runtime_root)
    dependencies["vision_workers"] = DependencyHealth(
        status="ok" if worker_count >= settings.infrasentinel_vision_workers else "warning",
        detail=f"{worker_count}/{settings.infrasentinel_vision_workers} workers running",
    )
    intelligence_running = _pid_file_running(runtime_root / "intelligence-worker.pid")
    dependencies["intelligence_worker"] = DependencyHealth(
        status="ok" if intelligence_running else "warning",
        detail="running" if intelligence_running else "not running",
    )

    try:
        with SessionLocal(bind=get_engine()) as db:
            models = list(db.scalars(select(VisionModel.availability)))
        available = sum(item == ModelAvailability.AVAILABLE for item in models)
        dependencies["vision_models"] = DependencyHealth(
            status="ok" if available else "warning",
            detail=f"{available}/{len(models)} configured models available",
        )
    except Exception as exc:
        dependencies["vision_models"] = DependencyHealth(
            status="unavailable", detail=type(exc).__name__
        )
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
