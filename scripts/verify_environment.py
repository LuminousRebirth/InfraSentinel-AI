from __future__ import annotations

import importlib
import json
import os
import platform
import shutil
import sys
from pathlib import Path

REQUIRED_MODULES = (
    "fastapi",
    "pydantic_settings",
    "sqlalchemy",
    "alembic",
    "psycopg",
    "redis",
    "cv2",
    "ultralytics",
    "torch",
)


def main() -> int:
    yolo_config_root = Path("runtime/ultralytics").resolve()
    yolo_config_root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("YOLO_CONFIG_DIR", str(yolo_config_root))
    missing = []
    for module in REQUIRED_MODULES:
        try:
            importlib.import_module(module)
        except Exception as exc:
            missing.append({"module": module, "error": type(exc).__name__})

    cuda_available = False
    if not any(item["module"] == "torch" for item in missing):
        import torch

        cuda_available = torch.cuda.is_available()

    conda_ffmpeg = Path(sys.prefix) / "Library" / "bin" / "ffmpeg.exe"
    report = {
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "platform": platform.platform(),
        "ffmpeg": shutil.which("ffmpeg") or (str(conda_ffmpeg) if conda_ffmpeg.exists() else None),
        "docker": shutil.which("docker"),
        "cuda_available": cuda_available,
        "missing_modules": missing,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if missing or sys.version_info[:2] != (3, 11) else 0


if __name__ == "__main__":
    raise SystemExit(main())
