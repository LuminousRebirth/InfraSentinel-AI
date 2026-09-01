"""通用工具：路径、日志、实验快照。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

# 项目根目录（src/vision_inspection/ -> 项目根）
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def resolve(path: str, base: Path | None = None) -> str:
    """把相对路径按 base（默认项目根）解析为绝对路径。"""
    base = base or PROJECT_ROOT
    p = Path(path)
    return str(p if p.is_absolute() else base / p)


def snapshot_config(cfg_path: str, output_dir: str) -> Path:
    """把本次训练用的配置快照复制到输出目录，保证实验可回溯。"""
    dest = Path(output_dir) / "config_snapshot.yaml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(cfg_path, dest)
    return dest


def save_metrics(metrics: dict, output_dir: str) -> Path:
    """保存训练指标为 JSON。"""
    dest = Path(output_dir) / "metrics.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest
