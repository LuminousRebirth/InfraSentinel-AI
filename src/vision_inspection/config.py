"""训练配置：从 configs/*.yaml 加载、校验、路径解析。

设计原则：超参进 YAML，代码只认 dataclass。改参 = 改配置文件，走 git 评审。
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path

import yaml

from .utils import resolve


@dataclass
class YoloConfig:
    """通用 YOLO 检测训练配置（safety / pipeline）。"""

    task: str
    model: str = "yolo26n.pt"
    data: str = ""
    output: str = "models/runs"
    epochs: int = 100
    imgsz: int = 640
    batch: int = 16
    device: int = 0
    workers: int = 4
    patience: int = 30
    lr0: float = 0.01
    optimizer: str = "auto"


@dataclass
class EquipmentConfig:
    """Anomalib 无监督异常检测配置。"""

    task: str = "equipment"
    categories: list = None
    backbone: str = "wide_resnet50_2"
    data_dir: str = "datasets/mvtec_anomaly_detection"
    output: str = "models/equipment"
    device: int = 0
    num_workers: int = 2

    def __post_init__(self):
        if self.categories is None:
            self.categories = ["bottle", "cable"]


@dataclass
class InspectionConfig:
    """巡检质检配置（照片质量 + 设备分类）。"""

    task: str = "inspection"
    blur_threshold: float = 50.0
    brightness_min: float = 60.0
    brightness_max: float = 200.0
    cls_model: str = "yolo26n-cls.pt"
    cls_data: str = "datasets/equipment_cls"
    cls_epochs: int = 50
    cls_imgsz: int = 224
    cls_output: str = "models/inspection/cls"


# task -> 配置类
_CONFIG_TYPES = {
    "safety": YoloConfig,
    "pipeline": YoloConfig,
    "equipment": EquipmentConfig,
    "inspection": InspectionConfig,
}


def load_config(path: str) -> object:
    """加载并校验 configs/*.yaml。相对路径按项目根解析为绝对路径。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}

    task = raw.get("task")
    cls = _CONFIG_TYPES.get(task)
    if cls is None:
        raise ValueError(f"未知 task: {task!r}，可用: {sorted(_CONFIG_TYPES)}")

    # 只取配置类认识的字段时间，忽略多余键
    valid = {f.name: raw[f.name] for f in fields(cls) if f.name in raw}
    cfg = cls(**valid)

    # 必填校验
    for field_name in getattr(cfg, "_required_", ["task"]):
        if not getattr(cfg, field_name):
            raise ValueError(f"配置缺失必填字段: {field_name}")

    # 相对路径解析
    if isinstance(cfg, YoloConfig):
        cfg.data = resolve(cfg.data)
        cfg.output = resolve(cfg.output)
    elif isinstance(cfg, EquipmentConfig):
        cfg.data_dir = resolve(cfg.data_dir)
        cfg.output = resolve(cfg.output)
    elif isinstance(cfg, InspectionConfig):
        cfg.cls_data = resolve(cfg.cls_data)
        cfg.cls_output = resolve(cfg.cls_output)

    return cfg
