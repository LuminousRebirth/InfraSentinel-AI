"""统一推理服务：按数据来源(scene)自动选择对应模型。

场景与数据来源一一对应:
  pipeline  ← CCTV/QV 检测车   管道缺陷识别(sewer-pipe-defects: CK/PL/SG/SL/TL/ZW)
  ppe       ← 厂区固定摄像头   安全行为识别(HHW: no_helmet/helmet)

推理后端: engine 优先（runs/export/<scene>/best.engine 存在时走 TensorRT），
否则回退 ultralytics PT，对外接口不变。
"""

from __future__ import annotations

from pathlib import Path

import cv2

from .model_config import SCENES
from .utils import PROJECT_ROOT

MODELS = PROJECT_ROOT / "models"
RUNS_MODELS = PROJECT_ROOT / "runs" / "models"

# 场景 → 训练数据集关键字（在 runs/models 下按训练 args.yaml 的 data 路径匹配对应权重）
SCENE_DATA_KEY = {
    "pipeline": "sewer",
    "ppe": "HHW",
}


def _find_best(task: str) -> Path:
    """定位权重：优先部署目录 models/<task>，回退到 runs/models 按训练数据集关键字匹配。"""
    # 1) 部署目录（手动拷贝权重到 models/ 时命中）
    root = MODELS / task
    candidates = sorted(root.rglob("best.pt")) if root.exists() else []
    # 2) 训练产物 runs/models/**：读取各训练目录 args.yaml 的 data 路径匹配场景
    if not candidates and RUNS_MODELS.exists():
        key = SCENE_DATA_KEY.get(task, task)
        for w in sorted(RUNS_MODELS.rglob("best.pt")):
            try:
                import yaml

                args = (
                    yaml.safe_load((w.parent.parent / "args.yaml").read_text(encoding="utf-8"))
                    or {}
                )
                data = str(args.get("data", ""))
            except Exception:
                continue
            if key.lower() in data.lower():
                candidates.append(w)
    if not candidates:
        raise FileNotFoundError(f"未找到 {task} 权重。请先训练:\n  python train_custom.py")
    return candidates[-1]


def _load_backend(scene: str, weights: Path | None, backend: str = "auto") -> tuple:
    """加载推理后端，返回 (model, kind)。

    backend="auto"：TensorRT 引擎存在则用 TRT，否则回退 PT。
    """
    cfg = SCENES[scene]
    if backend == "auto":
        backend = "trt" if cfg["engine"].exists() else "pt"
    if backend == "trt":
        from .trt_engine import TrtEngine

        if not cfg["engine"].exists():
            raise FileNotFoundError(
                f"TensorRT 引擎不存在: {cfg['engine']}（先运行 scripts/build_engine.py）"
            )
        return TrtEngine(cfg["engine"], cfg["names"], cfg["imgsz"]), "trt"
    from ultralytics import YOLO

    return YOLO(str(weights or _find_best(scene))), "pt"


class SceneHandler:
    """所有场景处理器的统一接口。predict(image) 返回统一结果 schema。"""

    def predict(self, image, conf: float = 0.35, save: bool = False) -> dict:
        raise NotImplementedError

    def _detect(self, image, conf: float, save: bool = False) -> list[dict]:
        """返回统一检测列表 [{"cls","conf","box"}]，TRT 与 PT 共用。"""
        if isinstance(image, (str, Path)):
            image = cv2.imread(str(image))  # 兼容路径输入（TRT 后端需要 numpy 数组）
        if self.backend == "trt":
            return self.model.detect(image, conf=conf)
        if save:
            # predict() 返回惰性生成器，必须消费才会实际推理+保存
            # save=True 走 YOLO 原生输出: runs/detect/predict/
            _ = list(self.model.predict(image, conf=conf, save=True, verbose=False))
        r = self.model(image, conf=conf, verbose=False)[0]
        return [
            {
                "cls": self.model.names[int(b.cls)],
                "conf": round(float(b.conf), 3),
                "box": [round(float(x), 1) for x in b.xyxy[0].tolist()],
            }
            for b in r.boxes
        ]


class PipelineHandler(SceneHandler):
    """管道缺陷识别：YOLO26n 检测（sewer-pipe-defects 6 类: CK/PL/SG/SL/TL/ZW）。"""

    def __init__(self, weights: Path | None = None, backend: str = "auto"):
        self.model, self.backend = _load_backend("pipeline", weights, backend)

    def predict(self, image, conf: float = 0.35, save: bool = False) -> dict:
        detections = self._detect(image, conf, save)
        return {
            "scene": "pipeline",
            "detections": detections,
            "anomaly_score": None,
            "quality": None,
            "violations": None,
            "report": None,
        }


class PpeHandler(SceneHandler):
    """安全行为识别：HHW 2 类（no_helmet/helmet），未戴安全帽即违规。"""

    VIOLATION_CLASSES = {"no_helmet"}

    def __init__(self, weights: Path | None = None, backend: str = "auto"):
        self.model, self.backend = _load_backend("ppe", weights, backend)

    def predict(self, image, conf: float = 0.35, save: bool = False) -> dict:
        detections = self._detect(image, conf, save)
        violations = [
            {"type": d["cls"], "conf": d["conf"]}
            for d in detections
            if d["cls"] in self.VIOLATION_CLASSES
        ]
        return {
            "scene": "ppe",
            "detections": detections,
            "anomaly_score": None,
            "quality": None,
            "violations": violations,
            "report": None,
        }


HANDLERS = {
    "pipeline": PipelineHandler,
    "ppe": PpeHandler,
}


def build_handlers(scene: str, backend: str = "auto") -> SceneHandler:
    if scene not in HANDLERS:
        raise KeyError(f"未知场景: {scene!r}，可用: {sorted(HANDLERS)}")
    return HANDLERS[scene](backend=backend)


def infer(scene: str, image, conf: float = 0.35, save: bool = False, backend: str = "auto") -> dict:
    """按 scene 自动选择模型；save=True 时输出到 runs/detect/predict/。"""
    return build_handlers(scene, backend).predict(image, conf=conf, save=save)
