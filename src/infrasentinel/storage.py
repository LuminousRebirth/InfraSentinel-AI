from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StorageStatus:
    root: Path
    free_gb: float
    total_gb: float
    warning: bool


def safe_path(root: Path, *parts: str) -> Path:
    """Resolve a child path and reject traversal or absolute-path escape."""

    resolved_root = root.resolve()
    candidate = resolved_root.joinpath(*parts).resolve()
    if not candidate.is_relative_to(resolved_root):
        raise ValueError("path escapes configured storage root")
    return candidate


def ensure_storage(root: Path, warning_gb: int) -> StorageStatus:
    root.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(root)
    gib = 1024**3
    return StorageStatus(
        root=root.resolve(),
        free_gb=round(usage.free / gib, 2),
        total_gb=round(usage.total / gib, 2),
        warning=usage.free / gib < warning_gb,
    )
