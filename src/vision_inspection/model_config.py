"""模型配置单一事实源：场景 → 权重 / 引擎 / 类别 / 输入尺寸 / 数据集。

infer.py、webapp/server.py 与 scripts/* 均从此处读取，避免重复定义。
"""

from __future__ import annotations

from .utils import PROJECT_ROOT

SCENES = {
    "ppe": {
        "pt": PROJECT_ROOT / "runs/models/ppe/HHW_noperson/finetune-4/weights/best.pt",
        "engine": PROJECT_ROOT / "runs/export/ppe/best.engine",
        "names": {0: "no_helmet", 1: "helmet"},
        "imgsz": 960,
        "data": PROJECT_ROOT / "datasets/ppe/HHW_detection_noperson/data.yaml",
    },
    "pipeline": {
        "pt": PROJECT_ROOT / "runs/models/pipeline/train/weights/best.pt",
        "engine": PROJECT_ROOT / "runs/export/pipeline/best.engine",
        "names": {0: "CK", 1: "PL", 2: "SG", 3: "SL", 4: "TL", 5: "ZW"},
        "imgsz": 640,
        "data": PROJECT_ROOT / "datasets/pipeline/sewer-pipe-defects/data.yaml",
    },
}
