"""统一训练入口：按 config.task 分发到对应训练器。

用法:
    python -m vision_inspection.cli train --config configs/safety.yaml
"""

from __future__ import annotations

from pathlib import Path

from .config import EquipmentConfig, InspectionConfig, YoloConfig, load_config
from .utils import snapshot_config


def _find_last_pt(output_dir: str) -> Path:
    """在输出目录下找最新的 last.pt 检查点（用于续跑）。"""
    pts = sorted(Path(output_dir).rglob("weights/last.pt"))
    if not pts:
        raise FileNotFoundError(f"未找到可续跑的检查点: {output_dir}")
    return pts[-1]


def train_yolo(cfg: YoloConfig, resume: bool = False) -> None:
    """YOLO 目标检测训练（safety / pipeline）。resume=True 时从上次断点继续。"""
    from ultralytics import YOLO

    if resume:
        last = _find_last_pt(cfg.output)
        print(f"[train] 从上次断点继续: {last}")
        YOLO(str(last)).train(resume=True)
        return

    assert Path(cfg.data).exists(), f"数据集配置不存在: {cfg.data}"
    print(f"[train] task={cfg.task} model={cfg.model} epochs={cfg.epochs} imgsz={cfg.imgsz}")

    model = YOLO(cfg.model)
    model.train(
        data=cfg.data,
        epochs=cfg.epochs,
        imgsz=cfg.imgsz,
        batch=cfg.batch,
        device=cfg.device,
        workers=cfg.workers,
        patience=cfg.patience,
        lr0=cfg.lr0,
        optimizer=cfg.optimizer,
        project=cfg.output,
        name="train",
    )
    best = Path(cfg.output) / "train" / "weights" / "best.pt"
    print(f"[train] 完成，最优权重: {best}")


def train_equipment(cfg: EquipmentConfig) -> None:
    """Anomalib PatchCore 无监督异常检测训练。"""
    import sys

    # 防 Windows GBK 控制台打印进度条 Unicode 符号崩溃
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from anomalib.data import MVTecAD
    from anomalib.engine import Engine
    from anomalib.models import Patchcore

    for category in cfg.categories:
        print(f"[train] equipment category={category} backbone={cfg.backbone}")
        datamodule = MVTecAD(root=cfg.data_dir, category=category, num_workers=cfg.num_workers)
        model = Patchcore(backbone=cfg.backbone)
        engine = Engine(
            default_root_dir=str(Path(cfg.output) / category), enable_progress_bar=False
        )
        engine.fit(model=model, datamodule=datamodule)
        print(f"[train] {category} 完成: {Path(cfg.output) / category}")


def train_inspection(cfg: InspectionConfig) -> None:
    """巡检质检：设备分类模型训练（需自建设备照片数据）。"""
    from ultralytics import YOLO

    if not Path(cfg.cls_data).exists():
        raise FileNotFoundError(
            f"设备分类数据不存在: {cfg.cls_data}\n"
            "请按 YOLO 分类格式准备: <cls_data>/{train,val}/{泵,阀门,电机,管线}/xxx.jpg"
        )
    model = YOLO(cfg.cls_model)
    model.train(
        data=str(Path(cfg.cls_data).parent),
        epochs=cfg.cls_epochs,
        imgsz=cfg.cls_imgsz,
        device=0,
        project=str(Path(cfg.cls_output).parent),
        name="cls",
        patience=20,
    )
    print(f"[train] 设备分类模型完成: {cfg.cls_output}")


def train(cfg_path: str, resume: bool = False) -> None:
    """按配置文件训练对应任务模型。resume=True 时从上次断点继续（仅 YOLO 任务）。"""
    cfg = load_config(cfg_path)

    if resume:
        if not isinstance(cfg, YoloConfig):
            raise ValueError("resume 仅支持 YOLO 训练任务（safety/pipeline）")
        train_yolo(cfg, resume=True)
        return

    # 实验快照：把本次配置复制到输出目录，保证可回溯
    output = getattr(cfg, "output", None) or getattr(cfg, "cls_output", "models/runs")
    snapshot_config(cfg_path, output)

    if isinstance(cfg, YoloConfig):
        train_yolo(cfg)
    elif isinstance(cfg, EquipmentConfig):
        train_equipment(cfg)
    elif isinstance(cfg, InspectionConfig):
        train_inspection(cfg)
    else:  # pragma: no cover
        raise TypeError(f"不支持的配置类型: {type(cfg)}")
