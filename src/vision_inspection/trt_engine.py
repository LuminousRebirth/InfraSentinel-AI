"""TensorRT 推理后端：加载 .engine 引擎做 YOLO 目标检测。

预处理（letterbox）与后处理（end2end conf 过滤）复用 ultralytics 实现，
保证与 PT 推理结果行为一致。

三个使用层次:
    TrtEngine   — 核心引擎：detect(img) → [{"cls","cls_idx","conf","box"}]（供 src 推理链）
    TrtModel    — webapp 兼容封装：predict(img) → [TrtResult]（模拟 ultralytics YOLO 接口）
    plot_detections — 画框工具（供 TrtResult.plot 与演示脚本共用）
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import tensorrt as trt
import torch
from ultralytics.data.augment import LetterBox
from ultralytics.utils.nms import non_max_suppression
from ultralytics.utils.ops import scale_boxes


def plot_detections(img_bgr: np.ndarray, dets: list[dict]) -> np.ndarray:
    """在图像上画检测框与标签，返回 BGR 图（不修改原图）。"""
    img = img_bgr.copy()
    for d in dets:
        x1, y1, x2, y2 = map(int, d["box"])
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(
            img,
            f"{d['cls']} {d['conf']:.2f}",
            (x1, max(0, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2,
        )
    return img


class TrtEngine:
    """固定 shape 的 YOLO 检测引擎（end2end 输出，已解码 (1, 300, 6)）。"""

    def __init__(self, engine_path: str | Path, names: dict[int, str], imgsz: int):
        self.names = names
        self.imgsz = imgsz

        # 反序列化引擎
        logger = trt.Logger(trt.Logger.WARNING)
        self.engine = trt.Runtime(logger).deserialize_cuda_engine(Path(engine_path).read_bytes())
        self.context = self.engine.create_execution_context()

        # 单输入单输出（TRT 10+ tensor 风格 API），输出布局 [x1,y1,x2,y2,conf,cls]
        self.out_name = next(
            self.engine.get_tensor_name(i)
            for i in range(self.engine.num_io_tensors)
            if self.engine.get_tensor_mode(self.engine.get_tensor_name(i))
            == trt.TensorIOMode.OUTPUT
        )
        self.out_shape = tuple(self.engine.get_tensor_shape(self.out_name))

    def infer_raw(self, img_bgr: np.ndarray) -> np.ndarray:
        """letterbox 预处理 → GPU 推理 → 输出 (1, 300, 6) 解码检测结果。"""
        # 与 ultralytics 一致的预处理：等比缩放留边 + BGR→RGB + /255
        # 注意 transpose 后必须 ascontiguousarray：TRT 按连续内存读取 data_ptr
        img = LetterBox(self.imgsz, auto=False, stride=32)(image=img_bgr)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        x = np.ascontiguousarray(img.transpose(2, 0, 1)[None], dtype=np.float32) / 255.0

        # GPU 缓冲（execute_v2 按 io tensor 顺序传设备指针，与 ultralytics backend 一致）
        x_t = torch.from_numpy(x).cuda()
        out_t = torch.empty(self.out_shape, dtype=torch.float32, device="cuda")
        self.context.execute_v2([x_t.data_ptr(), out_t.data_ptr()])
        return out_t.cpu().numpy()

    def detect(self, img_bgr: np.ndarray, conf: float = 0.35, iou: float = 0.7) -> list[dict]:
        """单图检测：conf 过滤（end2end 输出已解码，复用 ultralytics 逻辑）。

        返回 [{"cls": 类别名, "cls_idx": 类别索引, "conf": 置信度, "box": [x1,y1,x2,y2]}]
        """
        raw = torch.from_numpy(self.infer_raw(img_bgr))
        dets = non_max_suppression(raw, conf, iou)[0]  # (M, 6): xyxy, conf, cls
        if len(dets):
            dets[:, :4] = scale_boxes((self.imgsz, self.imgsz), dets[:, :4], img_bgr.shape[:2])

        return [
            {
                "cls": self.names[int(c)],
                "cls_idx": int(c),
                "conf": round(float(s), 3),
                "box": [round(float(v), 1) for v in xyxy],
            }
            for *xyxy, s, c in dets.tolist()
        ]


class TrtModel:
    """模拟 ultralytics YOLO 的最小接口，供 webapp 无缝替换：

    model.predict(img, conf=...) → [TrtResult]，TrtResult 提供
    orig_shape / boxes（b.cls/b.conf/b.xyxy）/ plot()。
    """

    def __init__(self, engine_path: str | Path, names: dict[int, str], imgsz: int):
        self.names = names
        self._engine = TrtEngine(engine_path, names, imgsz)

    def predict(self, image: np.ndarray, conf: float = 0.35, **_) -> list:
        return [TrtResult(image, self._engine.detect(image, conf=conf))]


class TrtResult:
    """模拟 ultralytics Results：仅含 webapp 用到的三个成员。"""

    def __init__(self, img: np.ndarray, dets: list[dict]):
        self.orig_shape = img.shape[:2]
        self.boxes = [_Box(d) for d in dets]
        self._img, self._dets = img, dets

    def plot(self) -> np.ndarray:
        """返回画框后的 BGR 图（ultralytics r.plot() 同款）。"""
        return plot_detections(self._img, self._dets)


class _Box:
    """模拟 ultralytics Boxes 的单个元素：cls(索引)/conf/xyxy。"""

    def __init__(self, det: dict):
        self.cls = det["cls_idx"]
        self.conf = det["conf"]
        self.xyxy = np.array([det["box"]], dtype=np.float32)
